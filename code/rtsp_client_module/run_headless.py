#!/usr/bin/env python3
"""
RTSP 클라이언트 모듈 - 헤드리스(GUI 없음) 실행파일
"""

import sys
import os
import logging
import time
import signal
import argparse
from datetime import datetime
from typing import List

# 현재 디렉토리를 Python path에 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

try:
    from rtsp_client_module import RTSPConfig, SharedPoolRTSPProcessor
    from rtsp_client_module.statistics import FrameCounter, ResourceMonitor, PerformanceProfiler
except ImportError as e:
    print(f"모듈 임포트 오류: {e}")
    print("필요한 의존성을 설치해주세요:")
    print("pip install opencv-python numpy psutil")
    sys.exit(1)

# 전역 변수
processor = None
running = False

def setup_logging(level='INFO'):
    """로깅 설정"""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('rtsp_processor.log')
        ]
    )

def signal_handler(sig, frame):
    """시그널 핸들러 (Ctrl+C 처리)"""
    global processor, running
    print('\n시그널 받음 - 종료 중...')
    running = False
    if processor:
        processor.stop()
    sys.exit(0)

def parse_arguments():
    """명령행 인자 파싱"""
    parser = argparse.ArgumentParser(description='RTSP 클라이언트 헤드리스 모드')
    
    parser.add_argument('--sources', '-s', 
                       nargs='+', 
                       default=None,
                       help='RTSP 소스 URL들 (여러 개 가능, 기본값: config.py의 sources 사용)')
    
    parser.add_argument('--threads', '-t', 
                       type=int, 
                       default=2,
                       help='스레드 수 (기본값: 2)')
    
    parser.add_argument('--duration', '-d', 
                       type=int, 
                       default=0,
                       help='실행 시간(초) - 0이면 무한 실행 (기본값: 0)')
    
    parser.add_argument('--save', 
                       action='store_true',
                       help='비디오 저장 활성화')
    
    parser.add_argument('--save-path', 
                       default='./output/',
                       help='비디오 저장 경로 (기본값: ./output/)')
    
    parser.add_argument('--blur-workers', 
                       type=int, 
                       default=1,
                       help='블러 워커 수 (기본값: 1)')
    
    parser.add_argument('--save-workers', 
                       type=int, 
                       default=1,
                       help='저장 워커 수 (기본값: 1)')
    
    parser.add_argument('--log-level', 
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       default='INFO',
                       help='로그 레벨 (기본값: INFO)')
    
    parser.add_argument('--fps', 
                       type=float, 
                       default=15.0,
                       help='입력 FPS (기본값: 15.0)')
    
    parser.add_argument('--no-blur', 
                       action='store_true',
                       help='블러 처리 비활성화')
    
    parser.add_argument('--frame-loss-rate', 
                       type=float, 
                       default=0.0,
                       help='프레임 손실률 시뮬레이션 (0.0-1.0, 기본값: 0.0)')
    
    # 2단계 저장 시스템 옵션
    parser.add_argument('--two-stage-storage', 
                       action='store_true',
                       help='2단계 저장 활성화 (SSD → HDD)')
    
    parser.add_argument('--file-move-workers', 
                       type=int, 
                       default=2,
                       help='파일 이동 워커 수 (기본값: 2)')
    
    return parser.parse_args()

def create_config(args) -> RTSPConfig:
    """인자에서 설정 생성"""
    # 기본 config 생성 (config.py의 기본값 사용)
    config = RTSPConfig()
    
    # 명령행 인자로 오버라이드
    if args.sources is not None:
        config.sources = args.sources
    
    config.thread_count = args.threads
    config.blur_workers = args.blur_workers
    config.save_workers = args.save_workers
    config.save_enabled = args.save
    config.save_path = args.save_path
    config.input_fps = args.fps
    config.blur_enabled = not args.no_blur
    config.frame_loss_rate = args.frame_loss_rate
    
    # 2단계 저장 시스템 설정
    config.two_stage_storage = args.two_stage_storage
    config.file_move_workers = args.file_move_workers
    
    if args.duration > 0:
        config.max_duration_seconds = args.duration
    
    return config

def print_status(processor: SharedPoolRTSPProcessor, start_time: float):
    """상태 출력"""
    elapsed = time.time() - start_time
    hours = int(elapsed // 3600)
    minutes = int((elapsed % 3600) // 60)
    seconds = int(elapsed % 60)
    
    print(f"\n=== 상태 정보 ===")
    print(f"실행 시간: {hours:02d}:{minutes:02d}:{seconds:02d}")
    print(f"프로세스 상태: {'실행 중' if processor.running else '중지됨'}")
    
    # 통계 정보 출력 (가능한 경우)
    try:
        stats = processor.stats_dict
        if stats:
            print("프레임 통계:")
            for key, value in stats.items():
                if 'received' in key:
                    print(f"  {key}: {value}")
    except:
        pass
    
    print("================\n")

def main():
    """메인 함수"""
    global processor, running
    
    # 인자 파싱
    args = parse_arguments()
    
    # 로깅 설정
    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)
    
    # 시그널 핸들러 등록
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("RTSP 클라이언트 모듈 - 헤드리스 모드 시작")
    logger.info(f"설정: {vars(args)}")
    
    try:
        # 설정 생성
        config = create_config(args)
        
        # 출력 디렉토리 생성
        if args.save:
            if config.two_stage_storage:
                # 2단계 저장: SSD와 HDD 경로 모두 생성
                os.makedirs(config.ssd_temp_path, exist_ok=True)
                os.makedirs(config.hdd_final_path, exist_ok=True)
                logger.info(f"2단계 저장 경로 생성:")
                logger.info(f"  📂 SSD 임시: {config.ssd_temp_path}")
                logger.info(f"  📁 HDD 최종: {config.hdd_final_path}")
            else:
                # 일반 저장
                os.makedirs(args.save_path, exist_ok=True)
                logger.info(f"저장 경로 생성: {args.save_path}")
        
        # 프로세서 생성 및 시작
        processor = SharedPoolRTSPProcessor(config)
        logger.info("프로세서 시작 중...")
        
        processor.start()
        running = True
        start_time = time.time()
        
        logger.info("RTSP 처리 시작됨")
        print("RTSP 처리가 시작되었습니다. Ctrl+C로 종료할 수 있습니다.")
        
        # 실행 시간 제한이 있는 경우
        if args.duration > 0:
            print(f"{args.duration}초간 실행 후 자동 종료됩니다.")
            
            # 상태 출력 간격 (10초마다)
            status_interval = 10
            last_status_time = 0
            
            while running and (time.time() - start_time) < args.duration:
                time.sleep(1)
                
                # 주기적 상태 출력
                if time.time() - last_status_time >= status_interval:
                    print_status(processor, start_time)
                    last_status_time = time.time()
            
            logger.info("설정된 시간 완료 - 종료")
        
        else:
            # 무한 실행
            print("무한 실행 모드입니다. Ctrl+C로 종료하세요.")
            
            # 상태 출력 간격 (30초마다)
            status_interval = 30
            last_status_time = 0
            
            while running:
                time.sleep(1)
                
                # 주기적 상태 출력
                if time.time() - last_status_time >= status_interval:
                    print_status(processor, start_time)
                    last_status_time = time.time()
    
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