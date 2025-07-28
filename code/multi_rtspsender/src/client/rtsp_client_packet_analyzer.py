#!/usr/bin/env python3
"""
RTSP 클라이언트 기반 RTP 패킷 분석기

완전한 RTSP 클라이언트 기능을 구현하여 MediaMTX 서버와 핸드셰이크한 후
RTP 패킷을 수신하여 손실률을 분석합니다.

사용법:
    python3 rtsp_client_packet_analyzer.py --url rtsp://10.2.10.158:1111/live
    python3 rtsp_client_packet_analyzer.py --url rtsp://10.2.10.158:1111/live --duration 60
"""

import socket
import struct
import argparse
import time
import re

class RTSPClient:
    """RTSP 클라이언트"""
    
    def __init__(self, url):
        self.url = url
        self.server_ip, self.server_port, self.path = self.parse_url(url)
        self.session_id = None
        self.cseq = 1
        self.rtp_port = None
        self.rtcp_port = None
        self.sock = None
        
    def parse_url(self, url):
        """RTSP URL 파싱"""
        if not url.startswith('rtsp://'):
            raise ValueError("RTSP URL은 rtsp://로 시작해야 합니다")
        
        url = url[7:]  # rtsp:// 제거
        
        if '/' in url:
            server_part, path = url.split('/', 1)
            path = '/' + path
        else:
            server_part = url
            path = '/'
        
        if ':' in server_part:
            ip, port_str = server_part.split(':')
            port = int(port_str)
        else:
            ip = server_part
            port = 554
        
        return ip, port, path
    
    def connect(self):
        """RTSP 서버에 연결"""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(10.0)
        try:
            self.sock.connect((self.server_ip, self.server_port))
            print(f"RTSP 서버 연결 성공: {self.server_ip}:{self.server_port}")
            return True
        except Exception as e:
            print(f"RTSP 서버 연결 실패: {e}")
            return False
    
    def send_request(self, method, additional_headers=None):
        """RTSP 요청 전송"""
        request = f"{method} {self.url} RTSP/1.0\r\n"
        request += f"CSeq: {self.cseq}\r\n"
        request += f"User-Agent: RTSPClientAnalyzer/1.0\r\n"
        
        if self.session_id and method != "DESCRIBE":
            request += f"Session: {self.session_id}\r\n"
        
        if additional_headers:
            for header, value in additional_headers.items():
                request += f"{header}: {value}\r\n"
        
        request += "\r\n"
        
        print(f"전송: {method} (CSeq: {self.cseq})")
        self.sock.send(request.encode())
        self.cseq += 1
        
        return self.receive_response()
    
    def send_setup_request(self, setup_url, additional_headers=None):
        """SETUP 요청 전송 (특별한 URL 사용)"""
        request = f"SETUP {setup_url} RTSP/1.0\r\n"
        request += f"CSeq: {self.cseq}\r\n"
        request += f"User-Agent: RTSPClientAnalyzer/1.0\r\n"
        
        if self.session_id:
            request += f"Session: {self.session_id}\r\n"
        
        if additional_headers:
            for header, value in additional_headers.items():
                request += f"{header}: {value}\r\n"
        
        request += "\r\n"
        
        print(f"전송: SETUP {setup_url} (CSeq: {self.cseq})")
        self.sock.send(request.encode())
        self.cseq += 1
        
        return self.receive_response()
    
    def receive_response(self):
        """RTSP 응답 수신"""
        response = b""
        while True:
            data = self.sock.recv(4096)
            if not data:
                break
            response += data
            
            # 헤더 끝 확인
            if b"\r\n\r\n" in response:
                break
        
        response_str = response.decode('utf-8', errors='ignore')
        return self.parse_response(response_str)
    
    def parse_response(self, response):
        """RTSP 응답 파싱"""
        lines = response.split('\r\n')
        if not lines:
            return None
        
        # 상태 라인 파싱
        status_line = lines[0]
        parts = status_line.split(' ', 2)
        if len(parts) < 3:
            return None
        
        status_code = int(parts[1])
        
        # 헤더 파싱
        headers = {}
        content = ""
        content_started = False
        
        for line in lines[1:]:
            if not content_started:
                if line == "":
                    content_started = True
                    continue
                if ':' in line:
                    key, value = line.split(':', 1)
                    headers[key.strip().lower()] = value.strip()
            else:
                content += line + '\n'
        
        return {
            'status_code': status_code,
            'headers': headers,
            'content': content.strip()
        }
    
    def describe(self):
        """DESCRIBE 요청 (SDP 가져오기)"""
        response = self.send_request("DESCRIBE", {
            "Accept": "application/sdp"
        })
        
        if response and response['status_code'] == 200:
            print("DESCRIBE 성공")
            return self.parse_sdp(response['content'])
        else:
            print(f"DESCRIBE 실패: {response['status_code'] if response else 'No response'}")
            return None
    
    def parse_sdp(self, sdp_content):
        """SDP 내용 파싱"""
        print("SDP 내용:")
        print(sdp_content)
        
        # 미디어 정보 추출
        media_info = {}
        lines = sdp_content.split('\n')
        
        for line in lines:
            line = line.strip()
            if line.startswith('m=video'):
                # m=video 0 RTP/AVP 96
                parts = line.split()
                if len(parts) >= 4:
                    media_info['media_type'] = 'video'
                    media_info['payload_type'] = parts[3]
            elif line.startswith('a=control:'):
                # a=control:trackID=0
                control_attr = line[10:]  # 'a=control:' 제거
                media_info['control'] = control_attr
                print(f"제어 URL: {control_attr}")
        
        return media_info
    
    def setup(self, media_info=None):
        """SETUP 요청 (RTP 세션 설정)"""
        # 임시 RTP/RTCP 포트 할당
        self.rtp_port = 5004
        self.rtcp_port = 5005
        
        transport = f"RTP/AVP/UDP;unicast;client_port={self.rtp_port}-{self.rtcp_port}"
        
        # 제어 URL 결정
        setup_url = self.url
        if media_info and 'control' in media_info:
            control = media_info['control']
            if control.startswith('rtsp://'):
                setup_url = control
            else:
                # 상대 경로인 경우 base URL에 추가
                setup_url = f"{self.url}/{control}"
        
        response = self.send_setup_request(setup_url, {
            "Transport": transport
        })
        
        if response and response['status_code'] == 200:
            print("SETUP 성공")
            
            # Session ID 추출
            if 'session' in response['headers']:
                self.session_id = response['headers']['session'].split(';')[0]
                print(f"세션 ID: {self.session_id}")
            
            # Transport 헤더에서 서버 포트 정보 추출
            if 'transport' in response['headers']:
                transport_info = response['headers']['transport']
                print(f"Transport: {transport_info}")
                
                # server_port 추출
                server_port_match = re.search(r'server_port=(\d+)-(\d+)', transport_info)
                if server_port_match:
                    server_rtp = int(server_port_match.group(1))
                    server_rtcp = int(server_port_match.group(2))
                    print(f"서버 RTP 포트: {server_rtp}, RTCP 포트: {server_rtcp}")
            
            return True
        else:
            print(f"SETUP 실패: {response['status_code'] if response else 'No response'}")
            return False
    
    def play(self):
        """PLAY 요청 (스트리밍 시작)"""
        response = self.send_request("PLAY")
        
        if response and response['status_code'] == 200:
            print("PLAY 성공 - 스트리밍 시작됨")
            return True
        else:
            print(f"PLAY 실패: {response['status_code'] if response else 'No response'}")
            return False
    
    def teardown(self):
        """TEARDOWN 요청 (세션 종료)"""
        if self.session_id:
            response = self.send_request("TEARDOWN")
            print("TEARDOWN 전송")
    
    def close(self):
        """연결 종료"""
        if self.sock:
            self.sock.close()

class RTPPacketAnalyzer:
    """RTP 패킷 분석기"""
    
    def __init__(self, rtp_port):
        self.rtp_port = rtp_port
        self.received_packets = 0
        self.total_bytes = 0
        self.sequence_numbers = set()
        self.min_seq = None
        self.max_seq = None
        self.start_time = None
        self.last_stats_time = None
        self.out_of_order_count = 0
        self.duplicate_count = 0
        self.last_received_seq = None
    
    def extract_rtp_sequence(self, data):
        """RTP 패킷에서 시퀀스 번호 추출"""
        if len(data) < 4:
            return None
        
        # RTP 헤더의 시퀀스 번호 (바이트 2-3)
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
        
        # 순서 확인 (16비트 순환 고려)
        if self.last_received_seq is not None:
            diff = (seq_num - self.last_received_seq) & 0xFFFF
            if diff > 32768:
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
        
        if not force and (current_time - self.last_stats_time) < 5.0:
            return
        
        self.last_stats_time = current_time
        runtime = current_time - self.start_time if self.start_time else 0
        
        stats = self.calculate_loss_statistics()
        
        print(f"\n=== RTP 패킷 손실 통계 (실행시간: {runtime:.1f}초) ===")
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
    
    def analyze_packets(self, duration=0):
        """RTP 패킷 분석"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(1.0)
        
        try:
            sock.bind(('', self.rtp_port))
            print(f"RTP 포트 {self.rtp_port}에서 패킷 수신 중...")
            
            self.start_time = time.time()
            self.last_stats_time = self.start_time
            
            end_time = None
            if duration > 0:
                end_time = self.start_time + duration
            
            while True:
                try:
                    if end_time and time.time() >= end_time:
                        print(f"\n{duration}초 분석 완료")
                        break
                    
                    data, addr = sock.recvfrom(65536)
                    seq_num = self.extract_rtp_sequence(data)
                    
                    if seq_num is not None:
                        self.update_statistics(seq_num, len(data))
                        self.print_statistics()
                
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"패킷 처리 오류: {e}")
                    continue
        
        except KeyboardInterrupt:
            print("\n분석 중단됨")
        
        finally:
            sock.close()
            
            # 최종 통계
            print("\n" + "=" * 60)
            print("최종 분석 결과")
            print("=" * 60)
            self.print_statistics(force=True)
            
            stats = self.calculate_loss_statistics()
            print(f"\n🎯 최종 손실률: {stats['loss_rate']:.2f}%")

class RTSPClientPacketAnalyzer:
    """RTSP 클라이언트 기반 패킷 분석기"""
    
    def __init__(self, url, duration=0):
        self.url = url
        self.duration = duration
        self.rtsp_client = None
        self.rtp_analyzer = None
    
    def run(self):
        """분석 실행"""
        print(f"RTSP 클라이언트 패킷 분석기 시작")
        print(f"URL: {self.url}")
        if self.duration > 0:
            print(f"분석 시간: {self.duration}초")
        print("-" * 60)
        
        # RTSP 클라이언트 생성 및 연결
        self.rtsp_client = RTSPClient(self.url)
        
        if not self.rtsp_client.connect():
            return
        
        try:
            # RTSP 핸드셰이크
            print("\n1. DESCRIBE 요청...")
            media_info = self.rtsp_client.describe()
            
            print("\n2. SETUP 요청...")
            if not self.rtsp_client.setup(media_info):
                return
            
            print("\n3. PLAY 요청...")
            if not self.rtsp_client.play():
                return
            
            # RTP 패킷 분석 시작
            print("\n4. RTP 패킷 분석 시작...")
            self.rtp_analyzer = RTPPacketAnalyzer(self.rtsp_client.rtp_port)
            self.rtp_analyzer.analyze_packets(self.duration)
            
        finally:
            # 정리
            if self.rtsp_client:
                self.rtsp_client.teardown()
                self.rtsp_client.close()

def main():
    parser = argparse.ArgumentParser(
        description='RTSP 클라이언트 기반 RTP 패킷 분석기',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  %(prog)s --url rtsp://10.2.10.158:1111/live          # 스트림 1 분석
  %(prog)s --url rtsp://10.2.10.158:1112/live          # 스트림 2 분석
  %(prog)s --url rtsp://10.2.10.158:1111/live --duration 60  # 60초간 분석
        """
    )
    
    parser.add_argument('--url', '-u', required=True,
                       help='RTSP 스트림 URL')
    
    parser.add_argument('--duration', '-d', type=int, default=0,
                       help='분석 시간 (초, 0=무제한)')
    
    args = parser.parse_args()
    
    try:
        analyzer = RTSPClientPacketAnalyzer(args.url, args.duration)
        analyzer.run()
    except Exception as e:
        print(f"오류: {e}")

if __name__ == '__main__':
    main()