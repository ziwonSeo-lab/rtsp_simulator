#!/usr/bin/env python3
"""
UDP 테스트 패킷 송신기

패킷 손실 계산기를 테스트하기 위한 UDP 패킷을 전송합니다.
"""

import socket
import struct
import time
import argparse

def send_test_packets(target_host, target_port, packet_count=100, delay=0.1, 
                     loss_simulation=0, seq_size=4, packet_format='simple'):
    """테스트 패킷 전송"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    try:
        print(f"UDP 테스트 패킷 전송 시작")
        print(f"대상: {target_host}:{target_port}")
        print(f"패킷 수: {packet_count}")
        print(f"전송 간격: {delay}초")
        print(f"시뮬레이션 손실률: {loss_simulation}%")
        print(f"패킷 형식: {packet_format}")
        print("-" * 40)
        
        sent_count = 0
        skipped_count = 0
        
        for seq in range(packet_count):
            # 손실 시뮬레이션 (특정 패킷 건너뛰기)
            if loss_simulation > 0 and (seq % (100 // loss_simulation)) == 0:
                skipped_count += 1
                print(f"패킷 {seq} 손실 시뮬레이션으로 건너뜀")
                continue
            
            # 패킷 데이터 생성
            if packet_format == 'rtp':
                # 간단한 RTP 헤더 시뮬레이션
                # 2바이트 헤더 + 2바이트 시퀀스 + 4바이트 타임스탬프 + 페이로드
                header = struct.pack('>BBH', 0x80, 96, seq & 0xFFFF)  # V=2, PT=96, SEQ
                timestamp = struct.pack('>I', int(time.time() * 1000) & 0xFFFFFFFF)
                payload = f"RTP_TEST_PACKET_{seq:06d}".encode()
                packet_data = header + timestamp + payload
            else:
                # 간단한 형식: 시퀀스 번호 + 페이로드
                if seq_size == 1:
                    seq_bytes = struct.pack('>B', seq & 0xFF)
                elif seq_size == 2:
                    seq_bytes = struct.pack('>H', seq & 0xFFFF)
                elif seq_size == 4:
                    seq_bytes = struct.pack('>I', seq & 0xFFFFFFFF)
                else:
                    seq_bytes = struct.pack('>Q', seq & 0xFFFFFFFFFFFFFFFF)
                
                payload = f"TEST_PACKET_{seq:06d}_DATA".encode()
                packet_data = seq_bytes + payload
            
            # 패킷 전송
            sock.sendto(packet_data, (target_host, target_port))
            sent_count += 1
            
            if seq % 10 == 0:
                print(f"전송됨: {seq}/{packet_count}")
            
            time.sleep(delay)
        
        print(f"\n전송 완료!")
        print(f"총 전송: {sent_count}개")
        print(f"시뮬레이션 손실: {skipped_count}개")
        print(f"실제 손실률: {(skipped_count/packet_count)*100:.2f}%")
        
    finally:
        sock.close()

def main():
    parser = argparse.ArgumentParser(description='UDP 테스트 패킷 송신기')
    
    parser.add_argument('--host', default='127.0.0.1', help='대상 호스트 (기본값: 127.0.0.1)')
    parser.add_argument('--port', '-p', type=int, required=True, help='대상 포트')
    parser.add_argument('--count', '-c', type=int, default=100, help='전송할 패킷 수 (기본값: 100)')
    parser.add_argument('--delay', '-d', type=float, default=0.1, help='패킷 간 지연 시간 (초, 기본값: 0.1)')
    parser.add_argument('--loss', '-l', type=int, default=0, help='시뮬레이션 손실률 %% (기본값: 0)')
    parser.add_argument('--seq-size', type=int, choices=[1, 2, 4, 8], default=4, help='시퀀스 번호 크기')
    parser.add_argument('--format', choices=['simple', 'rtp'], default='simple', help='패킷 형식')
    
    args = parser.parse_args()
    
    send_test_packets(
        target_host=args.host,
        target_port=args.port,
        packet_count=args.count,
        delay=args.delay,
        loss_simulation=args.loss,
        seq_size=args.seq_size,
        packet_format=args.format
    )

if __name__ == '__main__':
    main()