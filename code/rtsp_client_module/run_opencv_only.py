#!/usr/bin/env python3
"""
RTSP 클라이언트 모듈 - OpenCV만 사용 (FFmpeg 없음)
"""

import sys
import os
import logging
import time
import signal
import argparse

# 현재 디렉토리를 Python path에 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

try:
    from rtsp_client_module.config import RTSPConfig
    from rtsp_client_module.processor import SharedPoolRTSPProcessor
except ImportError as e:
    print(f"모듈 임포트 오류: {e}")
    sys.exit(1)

# 전역 변수
processor = None
running = False

def setup_logging(level='INFO'):
    """로깅 설정"""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

def signal_handler(sig, frame):
    """시그널 핸들러"""
    global processor, running
    print('\n종료 중...')
    running = False
    if processor:
        processor.stop()
    sys.exit(0)

def create_opencv_config(sources, **kwargs):
    """OpenCV만 사용하는 설정"""
    return RTSPConfig(
        sources=sources,
        thread_count=kwargs.get('threads', 2),
        blur_workers=1,
        save_workers=1,
        save_enabled=kwargs.get('save', False),
        save_path=kwargs.get('save_path', './output/'),
        
        # OpenCV 전용 설정
        save_format="avi",  # OpenCV가 잘 지원하는 포맷
        video_codec="XVID",  # OpenCV 기본 코덱
        
        # 성능 설정
        input_fps=15.0,
        preview_enabled=False,
        blur_enabled=True,
        
        # FFmpeg 관련 설정 비활성화
        hardware_acceleration="none",
        extra_options="",
        
        max_duration_seconds=kwargs.get('duration') if kwargs.get('duration', 0) > 0 else None
    )

def main():
    """메인 함수"""
    global processor, running
    
    parser = argparse.ArgumentParser(description='RTSP 클라이언트 - OpenCV 전용 모드')
    parser.add_argument('--sources', '-s', nargs='+', 
                       default=['rtsp://example.com/stream'], help='RTSP 소스')
    parser.add_argument('--threads', '-t', type=int, default=2, help='스레드 수')
    parser.add_argument('--duration', '-d', type=int, default=0, help='실행 시간(초)')
    parser.add_argument('--save', action='store_true', help='비디오 저장')
    parser.add_argument('--save-path', default='./output/', help='저장 경로')
    parser.add_argument('--log-level', default='INFO', help='로그 레벨')
    
    args = parser.parse_args()
    
    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print("=" * 60)
    print("🎥 OpenCV 전용 모드 (FFmpeg 없음)")
    print("   - AVI 포맷으로 저장")
    print("   - XVIV 코덱 사용")
    print("   - 기본 OpenCV 기능만 사용")
    print("=" * 60)
    
    try:
        config = create_opencv_config(
            sources=args.sources,
            threads=args.threads,
            duration=args.duration,
            save=args.save,
            save_path=args.save_path
        )
        
        if args.save:
            os.makedirs(args.save_path, exist_ok=True)
        
        processor = SharedPoolRTSPProcessor(config)
        processor.start()
        running = True
        start_time = time.time()
        
        logger.info("OpenCV 전용 모드로 시작됨")
        
        if args.duration > 0:
            while running and (time.time() - start_time) < args.duration:
                time.sleep(5)
        else:
            while running:
                time.sleep(30)
                elapsed = int(time.time() - start_time)
                print(f"[{elapsed:04d}s] OpenCV로 실행 중...")
    
    except Exception as e:
        logger.error(f"오류: {e}")
        return 1
    
    finally:
        running = False
        if processor:
            processor.stop()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())