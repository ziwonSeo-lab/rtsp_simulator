#!/usr/bin/env python3
"""
RTSP/RTP 패킷 분석기

원격 RTSP 서버의 RTP 스트림을 분석하여 패킷 손실률을 계산합니다.
RTSP 프로토콜을 통해 스트림 정보를 가져온 후 RTP 패킷을 수신하여 분석합니다.

사용법:
    python3 rtsp_rtp_packet_analyzer.py --url rtsp://10.2.10.158:1111/live
    python3 rtsp_rtp_packet_analyzer.py --url rtsp://10.2.10.158:1112/live --duration 60
"""

import socket
import struct
import argparse
import time

class RTSPRTPAnalyzer:
    """RTSP/RTP 패킷 분석기"""
    
    def __init__(self, rtsp_url, duration=0):
        self.rtsp_url = rtsp_url
        self.duration = duration
        
        # URL 파싱
        self.server_ip, self.rtsp_port, self.path = self.parse_rtsp_url(rtsp_url)
        
        # RTP 포트 계산 (RTSP 포트 기반)
        self.rtp_port = self.calculate_rtp_port(self.rtsp_port)
        
        # 통계 변수
        self.received_packets = 0
        self.total_bytes = 0
        self.sequence_numbers = set()
        self.min_seq = None
        self.max_seq = None
        self.start_time = None
        self.last_stats_time = None
        
        # RTP 관련
        self.out_of_order_count = 0
        self.duplicate_count = 0
        self.last_received_seq = None
        
    def parse_rtsp_url(self, url):
        """RTSP URL 파싱"""
        if not url.startswith('rtsp://'):
            raise ValueError("RTSP URL은 rtsp://로 시작해야 합니다")
        
        # rtsp:// 제거
        url = url[7:]
        
        # 경로 분리
        if '/' in url:
            server_part, path = url.split('/', 1)
            path = '/' + path
        else:
            server_part = url
            path = '/'
        
        # 포트 분리
        if ':' in server_part:
            ip, port_str = server_part.split(':')
            port = int(port_str)
        else:
            ip = server_part
            port = 554  # 기본 RTSP 포트
        
        return ip, port, path
    
    def calculate_rtp_port(self, rtsp_port):
        """RTSP 포트를 기반으로 RTP 포트 계산"""
        # MediaMTX 설정에 따른 RTP 포트 매핑
        port_mapping = {
            1111: 8000,  # Stream 1
            1112: 8002,  # Stream 2  
            1113: 8004,  # Stream 3
            1114: 8006,  # Stream 4
            1115: 8008,  # Stream 5
            1116: 8010   # Stream 6
        }
        
        if rtsp_port in port_mapping:
            return port_mapping[rtsp_port]
        else:
            # 기본 계산 방식 (일반적인 경우)
            return rtsp_port + 1000
    
    def extract_rtp_sequence(self, data):
        """RTP 패킷에서 시퀀스 번호 추출"""
        if len(data) < 4:
            return None
        
        # RTP 헤더 구조: V(2) + P(1) + X(1) + CC(4) + M(1) + PT(7) + Sequence(16)
        # 바이트 2-3에 시퀀스 번호가 있음 (big-endian)
        seq = struct.unpack('>H', data[2:4])[0]
        return seq
    
    def update_statistics(self, seq_num, packet_size):
        """통계 정보 업데이트"""
        current_time = time.time()
        
        if self.start_time is None:
            self.start_time = current_time
            self.last_stats_time = current_time
        
        self.received_packets += 1
        self.total_bytes += packet_size
        
        # 시퀀스 번호 범위 업데이트
        if self.min_seq is None or seq_num < self.min_seq:
            self.min_seq = seq_num
        if self.max_seq is None or seq_num > self.max_seq:
            self.max_seq = seq_num
        
        # 중복 패킷 확인
        if seq_num in self.sequence_numbers:
            self.duplicate_count += 1
        else:
            self.sequence_numbers.add(seq_num)
        
        # 순서 확인 (RTP 시퀀스는 순환함)
        if self.last_received_seq is not None:
            # 16비트 시퀀스 번호 순환 고려
            diff = (seq_num - self.last_received_seq) & 0xFFFF
            if diff > 32768:  # 역순으로 온 경우
                self.out_of_order_count += 1
        
        self.last_received_seq = seq_num
    
    def calculate_loss_statistics(self):
        """패킷 손실 통계 계산"""
        if self.min_seq is None or self.max_seq is None:
            return {
                'received_packets': 0,
                'unique_received': 0,
                'expected_packets': 0,
                'lost_packets': 0,
                'loss_rate': 0.0,
                'duplicate_packets': 0,
                'out_of_order_packets': 0,
                'min_seq': 0,
                'max_seq': 0,
                'total_bytes': 0
            }
        
        # RTP 시퀀스 번호 순환 고려
        if self.max_seq >= self.min_seq:
            expected_packets = self.max_seq - self.min_seq + 1
        else:
            # 시퀀스 번호가 순환한 경우
            expected_packets = (65536 - self.min_seq) + self.max_seq + 1
        
        unique_received = len(self.sequence_numbers)
        lost_packets = expected_packets - unique_received
        loss_rate = (lost_packets / expected_packets) * 100 if expected_packets > 0 else 0.0
        
        return {
            'received_packets': self.received_packets,
            'unique_received': unique_received,
            'expected_packets': expected_packets,
            'lost_packets': lost_packets,
            'loss_rate': loss_rate,
            'duplicate_packets': self.duplicate_count,
            'out_of_order_packets': self.out_of_order_count,
            'min_seq': self.min_seq,
            'max_seq': self.max_seq,
            'total_bytes': self.total_bytes
        }
    
    def print_statistics(self, force=False):
        """통계 정보 출력"""
        current_time = time.time()
        
        # 5초마다 또는 강제 출력
        if not force and (current_time - self.last_stats_time) < 5.0:
            return
        
        self.last_stats_time = current_time
        runtime = current_time - self.start_time if self.start_time else 0
        
        stats = self.calculate_loss_statistics()
        
        print(f"\n=== RTSP/RTP 패킷 손실 통계 (실행시간: {runtime:.1f}초) ===")
        print(f"RTSP URL: {self.rtsp_url}")
        print(f"RTP 포트: {self.rtp_port}")
        print(f"수신 패킷 수: {stats['received_packets']:,}")
        print(f"고유 패킷 수: {stats['unique_received']:,}")
        print(f"예상 패킷 수: {stats['expected_packets']:,}")
        print(f"손실 패킷 수: {stats['lost_packets']:,}")
        print(f"손실률: {stats['loss_rate']:.2f}%")
        print(f"중복 패킷: {stats['duplicate_packets']:,}")
        print(f"순서 뒤바뀜: {stats['out_of_order_packets']:,}")
        print(f"시퀀스 범위: {stats['min_seq']} ~ {stats['max_seq']}")
        print(f"총 수신 바이트: {stats['total_bytes']:,}")
        
        if runtime > 0:
            pps = stats['received_packets'] / runtime
            bps = stats['total_bytes'] / runtime
            print(f"수신률: {pps:.1f} packets/sec, {bps/1024:.1f} KB/sec")
        
        print("-" * 60)
    
    def run(self):
        """RTP 패킷 분석 실행"""
        print(f"RTSP/RTP 패킷 분석기 시작")
        print(f"RTSP URL: {self.rtsp_url}")
        print(f"서버: {self.server_ip}:{self.rtsp_port}")
        print(f"RTP 포트: {self.rtp_port}")
        if self.duration > 0:
            print(f"분석 시간: {self.duration}초")
        print("Ctrl+C로 종료...")
        print("-" * 60)
        
        # UDP 소켓 생성
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(1.0)  # 1초 타임아웃 설정
        
        try:
            # RTP 포트에 바인딩 (모든 인터페이스에서 수신)
            sock.bind(('', self.rtp_port))
            print(f"포트 {self.rtp_port}에 바인딩 성공, 패킷 대기 중...")
            
            # RTSP 연결 안내 메시지
            print(f"\n📺 RTSP 클라이언트로 스트림에 연결하세요:")
            print(f"   ffplay {self.rtsp_url}")
            print(f"   또는 VLC에서 {self.rtsp_url} 열기")
            print(f"\n패킷 수신을 시작하면 통계가 표시됩니다...")
            print("-" * 60)
            
            # 시작 시간 설정
            self.start_time = time.time()
            self.last_stats_time = self.start_time
            
            end_time = None
            if self.duration > 0:
                end_time = self.start_time + self.duration
            
            while True:
                try:
                    # 종료 시간 확인
                    if end_time and time.time() >= end_time:
                        print(f"\n{self.duration}초 분석 완료")
                        break
                    
                    data, addr = sock.recvfrom(65536)
                    
                    # RTP 시퀀스 번호 추출
                    seq_num = self.extract_rtp_sequence(data)
                    if seq_num is not None:
                        self.update_statistics(seq_num, len(data))
                        self.print_statistics()
                    
                except socket.timeout:
                    # 타임아웃 시 대기 상태 표시
                    if self.received_packets == 0:
                        current_time = time.time()
                        if self.start_time and (current_time - self.start_time) > 10:
                            if int(current_time) % 10 == 0:  # 10초마다 한 번씩 메시지
                                print("패킷 대기 중... RTSP 클라이언트가 연결되었는지 확인하세요.")
                    continue
                except Exception as e:
                    print(f"패킷 처리 오류: {e}")
                    continue
                    
        except KeyboardInterrupt:
            print("\n\n분석 종료...")
            
        finally:
            sock.close()
            
            # 최종 통계 출력
            print("\n" + "=" * 70)
            print("최종 분석 결과")
            print("=" * 70)
            self.print_statistics(force=True)
            
            # 손실률 요약
            stats = self.calculate_loss_statistics()
            print(f"\n🎯 최종 손실률: {stats['loss_rate']:.2f}%")
            print(f"📊 수신 효율: {stats['unique_received']}/{stats['expected_packets']} 패킷")

def main():
    parser = argparse.ArgumentParser(
        description='RTSP/RTP 패킷 분석기',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  %(prog)s --url rtsp://10.2.10.158:1111/live          # 스트림 1 분석
  %(prog)s --url rtsp://10.2.10.158:1112/live          # 스트림 2 분석  
  %(prog)s --url rtsp://10.2.10.158:1113/live --duration 60  # 60초간 분석
        """
    )
    
    parser.add_argument('--url', '-u', required=True,
                       help='RTSP 스트림 URL (예: rtsp://10.2.10.158:1111/live)')
    
    parser.add_argument('--duration', '-d', type=int, default=0,
                       help='분석 시간 (초, 0=무제한, 기본값: 0)')
    
    args = parser.parse_args()
    
    try:
        analyzer = RTSPRTPAnalyzer(args.url, args.duration)
        analyzer.run()
    except ValueError as e:
        print(f"오류: {e}")
    except Exception as e:
        print(f"예상치 못한 오류: {e}")

if __name__ == '__main__':
    main()