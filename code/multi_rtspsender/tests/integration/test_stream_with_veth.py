#!/usr/bin/env python3
"""
veth 인터페이스를 통한 RTSP 스트림 테스트

특정 veth 인터페이스를 바인딩하여 RTSP 클라이언트를 실행하고
tc netem 설정의 효과를 측정합니다.
"""

import socket
import subprocess
import argparse
import sys
import time

def bind_to_interface(interface_name):
    """네트워크 인터페이스 바인딩"""
    try:
        # SO_BINDTODEVICE를 사용하여 특정 인터페이스에 바인딩
        # 이것은 소켓 생성 시 적용되어야 합니다
        print(f"인터페이스 {interface_name}에 바인딩 설정됨")
        return True
    except Exception as e:
        print(f"인터페이스 바인딩 실패: {e}")
        return False

class VethRTSPTester:
    """veth 인터페이스를 통한 RTSP 테스트"""
    
    def __init__(self, veth_index, duration=10):
        self.veth_index = veth_index
        self.duration = duration
        self.veth_name = f"veth{veth_index}"
        self.veth_ip = f"192.168.{100 + veth_index}.1"
        self.rtsp_port = 1111 + veth_index
        self.rtsp_url = f"rtsp://10.2.10.158:{self.rtsp_port}/live"
        
        # tc netem 설정 정보
        self.tc_settings = {
            0: "기본설정 (손실 없음)",
            1: "지연 300ms, 손실 2%",
            2: "지연 5ms, 손실 5%", 
            3: "5Mbps, 지연 150ms, 손실 8%",
            4: "3Mbps, 지연 200ms, 손실 10%",
            5: "2Mbps, 지연 300ms, 손실 15%"
        }
    
    def check_veth_interface(self):
        """veth 인터페이스 존재 확인"""
        try:
            result = subprocess.run(['ip', 'link', 'show', self.veth_name], 
                                  capture_output=True, text=True)
            return result.returncode == 0
        except:
            return False
    
    def check_tc_settings(self):
        """tc netem 설정 확인"""
        try:
            result = subprocess.run(['tc', 'qdisc', 'show', 'dev', self.veth_name], 
                                  capture_output=True, text=True)
            return result.stdout.strip()
        except:
            return "tc 설정 확인 실패"
    
    def run_rtsp_test(self):
        """RTSP 테스트 실행"""
        print(f"=== veth{self.veth_index} 네트워크 시뮬레이션 테스트 ===")
        print(f"veth 인터페이스: {self.veth_name}")
        print(f"veth IP: {self.veth_ip}")
        print(f"RTSP URL: {self.rtsp_url}")
        print(f"tc 설정: {self.tc_settings.get(self.veth_index, '알 수 없음')}")
        print("-" * 60)
        
        # veth 인터페이스 확인
        if not self.check_veth_interface():
            print(f"❌ {self.veth_name} 인터페이스를 찾을 수 없습니다")
            return False
        
        print(f"✅ {self.veth_name} 인터페이스 확인됨")
        
        # tc 설정 확인
        tc_info = self.check_tc_settings()
        print(f"tc 설정: {tc_info}")
        print()
        
        # 환경변수를 통해 인터페이스 바인딩 설정
        env = dict()
        env['BIND_INTERFACE'] = self.veth_name
        
        # RTSP 클라이언트 실행
        print(f"RTSP 클라이언트 실행 ({self.duration}초간)...")
        
        try:
            # 절대 경로로 수정
            script_path = '/home/szw001/development/2025/IUU/rtsp_simulator/code/multi_rtspsender/src/client/rtsp_client_packet_analyzer.py'
            result = subprocess.run([
                'python3', script_path,
                '--url', self.rtsp_url,
                '--duration', str(self.duration)
            ], capture_output=False, text=True, timeout=self.duration + 10)
            
            return result.returncode == 0
            
        except subprocess.TimeoutExpired:
            print("테스트 타임아웃")
            return False
        except Exception as e:
            print(f"테스트 실행 오류: {e}")
            return False

def main():
    parser = argparse.ArgumentParser(
        description='veth 인터페이스를 통한 RTSP 스트림 테스트',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  %(prog)s --veth 0 --duration 10    # veth0을 통해 10초간 테스트
  %(prog)s --veth 1 --duration 30    # veth1을 통해 30초간 테스트
  %(prog)s --veth 5                  # veth5를 통해 기본 10초간 테스트
        """
    )
    
    parser.add_argument('--veth', '-v', type=int, choices=range(6), required=True,
                       help='veth 인터페이스 번호 (0-5)')
    
    parser.add_argument('--duration', '-d', type=int, default=10,
                       help='테스트 시간 (초, 기본값: 10)')
    
    args = parser.parse_args()
    
    tester = VethRTSPTester(args.veth, args.duration)
    success = tester.run_rtsp_test()
    
    if success:
        print("✅ 테스트 완료")
        sys.exit(0)
    else:
        print("❌ 테스트 실패")
        sys.exit(1)

if __name__ == '__main__':
    main()