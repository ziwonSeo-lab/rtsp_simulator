"""
RTSP 클라이언트 모듈 사용 예제
"""

import logging
import time
from rtsp_client_module import RTSPConfig, SharedPoolRTSPProcessor, create_gui

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def example_basic_usage():
    """기본 사용법 예제"""
    print("=== RTSP 클라이언트 모듈 기본 사용법 ===")
    
    # 1. 설정 생성
    sources = [
        "rtsp://example.com/stream1",
        "rtsp://example.com/stream2"
    ]
    
    config = RTSPConfig(
        sources=sources,
        thread_count=2,
        blur_workers=1,
        save_workers=1,
        save_enabled=True,
        save_path="./output/"
    )
    
    # 2. 프로세서 생성 및 시작
    processor = SharedPoolRTSPProcessor(config)
    
    try:
        print("프로세서 시작...")
        processor.start()
        
        # 3. 잠깐 실행
        print("10초간 실행...")
        time.sleep(10)
        
    finally:
        # 4. 프로세서 종료
        print("프로세서 종료...")
        processor.stop()
        print("완료!")


def example_gui_usage():
    """GUI 사용법 예제"""
    print("=== RTSP 클라이언트 GUI 사용법 ===")
    
    # GUI 생성 및 실행
    root, app = create_gui()
    print("GUI 시작됨. 윈도우를 닫으면 종료됩니다.")
    root.mainloop()


def example_statistics_usage():
    """통계 모듈 사용법 예제"""
    print("=== 통계 모듈 사용법 ===")
    
    from rtsp_client_module import FrameStatistics, FrameCounter, ResourceMonitor
    
    # 프레임 통계
    stats = FrameStatistics()
    stats.increment_received()
    stats.increment_processed()
    print("프레임 통계:", stats.get_stats())
    
    # 프레임 카운터
    counter = FrameCounter()
    counter.increment()
    print("프레임 수:", counter.get_count())
    print("FPS:", counter.get_fps())
    
    # 리소스 모니터
    monitor = ResourceMonitor()
    monitor.start_monitoring()
    time.sleep(2)  # 잠깐 모니터링
    print("현재 리소스:", monitor.get_current_stats())
    monitor.stop_monitoring()


if __name__ == "__main__":
    print("RTSP 클라이언트 모듈 예제")
    print("1. 기본 사용법")
    print("2. GUI 사용법") 
    print("3. 통계 모듈 사용법")
    
    choice = input("선택하세요 (1-3): ").strip()
    
    if choice == "1":
        example_basic_usage()
    elif choice == "2":
        example_gui_usage()
    elif choice == "3":
        example_statistics_usage()
    else:
        print("잘못된 선택입니다.")