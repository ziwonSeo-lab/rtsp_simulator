#!/usr/bin/env python3
"""
RTSP 클라이언트 모듈 - 안정화된 실행파일
H.264 디코딩 에러를 최소화하는 설정 포함
"""

import sys
import os
import logging
import time
import signal
import argparse
from datetime import datetime

# 현재 디렉토리를 Python path에 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

try:
    from rtsp_client_module import RTSPConfig, SharedPoolRTSPProcessor
except ImportError as e:
    print(f"모듈 임포트 오류: {e}")
    print("필요한 의존성을 설치해주세요:")
    print("pip install opencv-python numpy psutil")
    sys.exit(1)

# 전역 변수
processor = None
running = False

def setup_logging(level='INFO'):
    """로깅 설정 - H.264 디코딩 에러 필터링"""
    
    class H264ErrorFilter(logging.Filter):
        """H.264 디코딩 에러를 필터링하는 클래스"""
        def filter(self, record):
            # H.264 관련 에러 메시지들을 필터링
            h264_errors = [
                'corrupted macroblock',
                'error while decoding MB',
                'Invalid level prefix',
                'out of range intra chroma pred mode',
                '[h264 @'
            ]
            
            message = record.getMessage()
            for error in h264_errors:
                if error in message:
                    return False
            return True
    
    # 로거 설정
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, level.upper()))
    
    # 기존 핸들러 제거
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # 새 핸들러 생성
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # 콘솔 핸들러
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(H264ErrorFilter())
    logger.addHandler(console_handler)
    
    # 파일 핸들러 (모든 로그 저장)
    file_handler = logging.FileHandler('rtsp_processor_full.log')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

def signal_handler(sig, frame):
    """시그널 핸들러 (Ctrl+C 처리)"""
    global processor, running
    print('\n시그널 받음 - 종료 중...')
    running = False
    if processor:
        processor.stop()
    sys.exit(0)

def create_stable_config(sources, threads=2, duration=0, save=False, save_path='./output/'):
    """안정화된 RTSP 설정 생성"""
    return RTSPConfig(
        sources=sources,
        thread_count=threads,
        blur_workers=1,
        save_workers=1,
        save_enabled=save,
        save_path=save_path,
        
        # 안정성을 위한 설정들
        input_fps=10.0,  # FPS 낮춤
        force_fps=True,
        connection_timeout=15,  # 연결 타임아웃 증가
        reconnect_interval=3,   # 재연결 간격 단축
        frame_loss_rate=0.0,    # 프레임 손실 시뮬레이션 비활성화
        
        # 큐 크기 조정
        blur_queue_size=500,    # 큐 크기 줄임
        save_queue_size=500,
        preview_queue_size=25,
        processing_queue_size=500,
        
        # 블러 간격 조정
        blur_interval=5,        # 블러 처리 간격 증가
        
        # FFmpeg 안정화 설정
        video_codec="libx264",
        quality_mode="cbr",
        bitrate="1M",           # 비트레이트 낮춤
        compression_level=4,    # 압축 레벨 낮춤
        ffmpeg_preset="ultrafast",  # 빠른 인코딩
        pixel_format="yuv420p",
        
        # 기타 안정화 설정
        blur_enabled=True,
        preview_enabled=False,  # 프리뷰 비활성화로 성능 향상
        high_performance_mode=True,
        
        max_duration_seconds=duration if duration > 0 else None
    )

def main():
    """메인 함수"""
    global processor, running
    
    parser = argparse.ArgumentParser(description='RTSP 클라이언트 안정화 모드')
    parser.add_argument('--sources', '-s', nargs='+', 
                       default=['rtsp://example.com/stream'],
                       help='RTSP 소스 URL들')
    parser.add_argument('--threads', '-t', type=int, default=2, help='스레드 수')
    parser.add_argument('--duration', '-d', type=int, default=0, 
                       help='실행 시간(초) - 0이면 무한 실행')
    parser.add_argument('--save', action='store_true', help='비디오 저장 활성화')
    parser.add_argument('--save-path', default='./output/', help='저장 경로')
    parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       default='INFO', help='로그 레벨')
    
    args = parser.parse_args()
    
    # 로깅 설정 (H.264 에러 필터링 포함)
    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)
    
    # 시그널 핸들러 등록
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("RTSP 클라이언트 모듈 - 안정화 모드 시작")
    logger.info(f"설정: {vars(args)}")
    
    try:
        # 안정화된 설정 생성
        config = create_stable_config(
            sources=args.sources,
            threads=args.threads,
            duration=args.duration,
            save=args.save,
            save_path=args.save_path
        )
        
        # 출력 디렉토리 생성
        if args.save:
            os.makedirs(args.save_path, exist_ok=True)
            logger.info(f"저장 경로 생성: {args.save_path}")
        
        # 프로세서 생성 및 시작
        processor = SharedPoolRTSPProcessor(config)
        logger.info("프로세서 시작 중...")
        
        processor.start()
        running = True
        start_time = time.time()
        
        logger.info("RTSP 처리 시작됨 (안정화 모드)")
        print("=" * 60)
        print("🔧 안정화 모드로 실행 중")
        print("   - H.264 디코딩 에러 필터링 활성화")
        print("   - 낮은 FPS (10fps)로 안정성 우선")
        print("   - 작은 큐 크기로 메모리 사용량 최소화")
        print("   - 빠른 FFmpeg 인코딩 설정")
        print("=" * 60)
        print("Ctrl+C로 종료할 수 있습니다.")
        
        # 실행 시간 제한이 있는 경우
        if args.duration > 0:
            print(f"{args.duration}초간 실행 후 자동 종료됩니다.")
            
            while running and (time.time() - start_time) < args.duration:
                time.sleep(5)  # 5초마다 체크
                
                # 간단한 상태 출력
                elapsed = int(time.time() - start_time)
                remaining = args.duration - elapsed
                if elapsed % 30 == 0:  # 30초마다 상태 출력
                    print(f"[{elapsed:04d}s] 실행 중... (남은 시간: {remaining}초)")
            
            logger.info("설정된 시간 완료 - 종료")
        
        else:
            # 무한 실행
            print("무한 실행 모드입니다.")
            
            while running:
                time.sleep(30)  # 30초마다 체크
                elapsed = int(time.time() - start_time)
                hours = elapsed // 3600
                minutes = (elapsed % 3600) // 60
                seconds = elapsed % 60
                print(f"[{hours:02d}:{minutes:02d}:{seconds:02d}] 안정적으로 실행 중...")
    
    except KeyboardInterrupt:
        logger.info("키보드 인터럽트로 종료")
    
    except Exception as e:
        logger.error(f"오류 발생: {e}")
        return 1
    
    finally:
        # 정리
        running = False
        if processor:
            logger.info("프로세서 종료 중...")
            processor.stop()
            logger.info("프로세서 종료 완료")
        
        print("RTSP 클라이언트 종료됨")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())