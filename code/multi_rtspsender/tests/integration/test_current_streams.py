#!/usr/bin/env python3
"""
현재 MediaMTX 스트림들의 기본 패킷 손실률 테스트

veth 설정 없이도 현재 6개 스트림이 모두 정상적으로 작동하는지 확인하고
기본 네트워크 상태에서의 패킷 손실률을 측정합니다.
"""

import subprocess
import time
import argparse

def test_stream(stream_num, duration=10):
    """개별 스트림 테스트"""
    rtsp_port = 1111 + stream_num - 1  # 1-6을 1111-1116으로 변환
    rtsp_url = f"rtsp://10.2.10.158:{rtsp_port}/live"
    
    print(f"=== 스트림 {stream_num} 테스트 ===")
    print(f"RTSP URL: {rtsp_url}")
    print(f"테스트 시간: {duration}초")
    print("-" * 50)
    
    try:
        # RTSP 클라이언트 실행
        result = subprocess.run([
            'python3', '../../src/client/rtsp_client_packet_analyzer.py',
            '--url', rtsp_url,
            '--duration', str(duration)
        ], capture_output=False, text=True, timeout=duration + 10)
        
        success = result.returncode == 0
        print(f"스트림 {stream_num} 결과: {'✅ 성공' if success else '❌ 실패'}")
        return success
        
    except subprocess.TimeoutExpired:
        print(f"스트림 {stream_num} 결과: ⏰ 타임아웃")
        return False
    except Exception as e:
        print(f"스트림 {stream_num} 결과: ❌ 오류 - {e}")
        return False

def test_all_streams(duration=10):
    """모든 스트림 순차 테스트"""
    print("🧪 MediaMTX 스트림 기본 테스트 시작")
    print(f"각 스트림을 {duration}초씩 테스트합니다...")
    print("=" * 60)
    
    results = []
    
    for i in range(1, 7):  # 스트림 1-6
        print(f"\n[{i}/6] 스트림 {i} 테스트 중...")
        success = test_stream(i, duration)
        results.append((i, success))
        
        if i < 6:  # 마지막이 아니면 잠시 대기
            print("\n다음 스트림 테스트까지 2초 대기...")
            time.sleep(2)
    
    # 결과 요약
    print("\n" + "=" * 60)
    print("🏁 전체 테스트 결과 요약")
    print("=" * 60)
    
    success_count = 0
    for stream_num, success in results:
        status = "✅ 성공" if success else "❌ 실패"
        print(f"스트림 {stream_num} (포트 {1110 + stream_num}): {status}")
        if success:
            success_count += 1
    
    print(f"\n📊 성공률: {success_count}/6 ({success_count/6*100:.1f}%)")
    
    if success_count == 6:
        print("\n🎉 모든 스트림이 정상적으로 작동합니다!")
        print("   이제 veth 인터페이스를 설정하면 네트워크 시뮬레이션 효과를 측정할 수 있습니다.")
        print("   manual_veth_setup.md 파일을 참조하여 veth를 설정하세요.")
    else:
        print(f"\n⚠️  {6 - success_count}개 스트림에 문제가 있습니다.")
        print("   MediaMTX 서버 상태를 확인해주세요.")

def main():
    parser = argparse.ArgumentParser(
        description='MediaMTX 스트림 기본 테스트',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  %(prog)s                           # 모든 스트림 10초씩 테스트
  %(prog)s --duration 5              # 모든 스트림 5초씩 테스트
  %(prog)s --stream 1 --duration 15  # 스트림 1만 15초 테스트
        """
    )
    
    parser.add_argument('--stream', '-s', type=int, choices=range(1, 7),
                       help='특정 스트림만 테스트 (1-6)')
    
    parser.add_argument('--duration', '-d', type=int, default=10,
                       help='각 스트림 테스트 시간 (초, 기본값: 10)')
    
    args = parser.parse_args()
    
    if args.stream:
        # 개별 스트림 테스트
        test_stream(args.stream, args.duration)
    else:
        # 전체 스트림 테스트
        test_all_streams(args.duration)

if __name__ == '__main__':
    main()