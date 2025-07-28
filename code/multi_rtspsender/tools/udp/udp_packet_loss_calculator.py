#!/usr/bin/env python3
"""
UDP 패킷 손실 계산 도구

socket, struct, argparse, time 모듈만을 사용하여 UDP 패킷의 손실률을 계산합니다.
시퀀스 번호를 기반으로 누락된 패킷을 감지하고 실시간 통계를 제공합니다.

사용법:
    python3 udp_packet_loss_calculator.py --port 8000
    python3 udp_packet_loss_calculator.py --port 8000 --format rtp
    python3 udp_packet_loss_calculator.py --port 8000 --seq-offset 4 --seq-size 2
"""

import socket
import struct
import argparse
import time

class UDPPacketLossCalculator:
    """UDP 패킷 손실 계산기"""
    
    def __init__(self, host='', port=0, seq_offset=0, seq_size=4, byte_order='big', packet_format='simple'):
        self.host = host
        self.port = port
        self.seq_offset = seq_offset
        self.seq_size = seq_size
        self.byte_order = byte_order
        self.packet_format = packet_format
        
        # 통계 변수
        self.received_packets = 0
        self.total_bytes = 0
        self.sequence_numbers = set()
        self.min_seq = None
        self.max_seq = None
        self.start_time = None
        self.last_stats_time = None
        
        # 실시간 추적
        self.last_received_seq = None
        self.out_of_order_count = 0
        self.duplicate_count = 0
        
        # struct 형식 설정
        self.struct_format = self._get_struct_format()
        
    def _get_struct_format(self):
        """struct 언패킹 형식 생성"""
        endian = '>' if self.byte_order == 'big' else '<'
        
        if self.seq_size == 1:
            return f'{endian}B'  # unsigned char
        elif self.seq_size == 2:
            return f'{endian}H'  # unsigned short
        elif self.seq_size == 4:
            return f'{endian}I'  # unsigned int
        elif self.seq_size == 8:
            return f'{endian}Q'  # unsigned long long
        else:
            raise ValueError(f"지원하지 않는 시퀀스 크기: {self.seq_size}")
    
    def extract_sequence_number(self, data):
        """패킷 데이터에서 시퀀스 번호 추출"""
        if len(data) < self.seq_offset + self.seq_size:
            return None
            
        if self.packet_format == 'rtp':
            # RTP 헤더에서 시퀀스 번호 추출 (2바이트, 오프셋 2)
            if len(data) < 4:
                return None
            seq = struct.unpack('>H', data[2:4])[0]
            return seq
        else:
            # 일반 형식: 지정된 오프셋에서 시퀀스 번호 추출
            seq_data = data[self.seq_offset:self.seq_offset + self.seq_size]
            seq = struct.unpack(self.struct_format, seq_data)[0]
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
        
        # 순서 확인
        if self.last_received_seq is not None:
            if seq_num < self.last_received_seq:
                self.out_of_order_count += 1
        
        self.last_received_seq = seq_num
    
    def calculate_loss_statistics(self):
        """패킷 손실 통계 계산"""
        if self.min_seq is None or self.max_seq is None:
            return {
                'received_packets': 0,
                'expected_packets': 0,
                'lost_packets': 0,
                'loss_rate': 0.0,
                'duplicate_packets': 0,
                'out_of_order_packets': 0
            }
        
        # 예상 패킷 수 계산 (시퀀스 번호 범위 기반)
        expected_packets = self.max_seq - self.min_seq + 1
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
        
        print(f"\n=== UDP 패킷 손실 통계 (실행시간: {runtime:.1f}초) ===")
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
        
        print("-" * 50)
    
    def find_missing_sequences(self):
        """누락된 시퀀스 번호 찾기"""
        if self.min_seq is None or self.max_seq is None:
            return []
        
        expected_set = set(range(self.min_seq, self.max_seq + 1))
        missing = sorted(expected_set - self.sequence_numbers)
        return missing
    
    def run(self):
        """UDP 서버 실행"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            sock.bind((self.host, self.port))
            actual_host = self.host if self.host else '0.0.0.0'
            print(f"UDP 패킷 손실 계산기 시작")
            print(f"바인딩 주소: {actual_host}:{self.port}")
            print(f"패킷 형식: {self.packet_format}")
            print(f"시퀀스 오프셋: {self.seq_offset}, 크기: {self.seq_size}바이트")
            print(f"바이트 순서: {self.byte_order}-endian")
            print("Ctrl+C로 종료...")
            print("-" * 50)
            
            while True:
                try:
                    data, addr = sock.recvfrom(65536)
                    
                    # 시퀀스 번호 추출
                    seq_num = self.extract_sequence_number(data)
                    if seq_num is not None:
                        self.update_statistics(seq_num, len(data))
                        self.print_statistics()
                    
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"패킷 처리 오류: {e}")
                    continue
                    
        except KeyboardInterrupt:
            print("\n\n프로그램 종료 중...")
            
        finally:
            sock.close()
            
            # 최종 통계 출력
            print("\n" + "=" * 60)
            print("최종 통계 결과")
            print("=" * 60)
            self.print_statistics(force=True)
            
            # 누락된 시퀀스 번호 표시 (처음 20개만)
            missing = self.find_missing_sequences()
            if missing:
                print(f"\n누락된 시퀀스 번호 (처음 20개):")
                print(missing[:20])
                if len(missing) > 20:
                    print(f"... 총 {len(missing)}개 누락")

def main():
    parser = argparse.ArgumentParser(
        description='UDP 패킷 손실 계산 도구',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  %(prog)s --port 8000                    # 로컬 포트 8000에서 수신
  %(prog)s --host 0.0.0.0 --port 8000     # 모든 인터페이스에서 수신
  %(prog)s --host 192.168.1.100 --port 8000 # 특정 IP에서 수신
  %(prog)s --port 8000 --format rtp       # RTP 패킷 형식
  %(prog)s --port 8000 --seq-offset 4     # 시퀀스 오프셋 4바이트
  %(prog)s --port 8000 --seq-size 2       # 2바이트 시퀀스 번호
  %(prog)s --port 8000 --byte-order little # 리틀 엔디안
        """
    )
    
    parser.add_argument('--host', default='', 
                       help='바인딩할 호스트 IP (기본값: 모든 인터페이스)')
    
    parser.add_argument('--port', '-p', type=int, required=True,
                       help='UDP 수신 포트 번호')
    
    parser.add_argument('--format', choices=['simple', 'rtp'], default='simple',
                       help='패킷 형식 (기본값: simple)')
    
    parser.add_argument('--seq-offset', type=int, default=0,
                       help='시퀀스 번호 오프셋 (바이트, 기본값: 0)')
    
    parser.add_argument('--seq-size', type=int, choices=[1, 2, 4, 8], default=4,
                       help='시퀀스 번호 크기 (바이트, 기본값: 4)')
    
    parser.add_argument('--byte-order', choices=['big', 'little'], default='big',
                       help='바이트 순서 (기본값: big)')
    
    args = parser.parse_args()
    
    # RTP 형식인 경우 시퀀스 설정 자동 조정
    if args.format == 'rtp':
        args.seq_offset = 2
        args.seq_size = 2
        args.byte_order = 'big'
    
    calculator = UDPPacketLossCalculator(
        host=args.host,
        port=args.port,
        seq_offset=args.seq_offset,
        seq_size=args.seq_size,
        byte_order=args.byte_order,
        packet_format=args.format
    )
    
    calculator.run()

if __name__ == '__main__':
    main()