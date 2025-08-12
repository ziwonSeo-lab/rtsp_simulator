#!/usr/bin/env python3
"""
RTSP Multithread Processor 실행 스크립트

실제 운영용 실행 파일
- 환경변수 기반 설정
- 안정적인 에러 처리
- 신호 처리
- 로깅 설정
"""

import os
import sys
import signal
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
# 패키지 경로 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

def setup_logging():
    """로깅 설정"""
    log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
    log_file = os.getenv('LOG_FILE', 'rtsp_processor.log')
    
    # 로그 레벨 검증
    numeric_level = getattr(logging, log_level, logging.INFO)
    
    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding='utf-8')
        ]
    )
    
    return logging.getLogger(__name__)

def validate_environment():
    """환경변수 검증"""
    logger = logging.getLogger(__name__)
    
    # 필수 환경변수 확인
    rtsp_url = os.getenv('RTSP_URL')
    if not rtsp_url:
        logger.error("❌ RTSP_URL 환경변수가 설정되지 않았습니다")
        logger.info("다음 중 하나의 방법으로 설정하세요:")
        logger.info("1. export RTSP_URL='rtsp://your-camera-ip:554/stream'")
        logger.info("2. source setup_env.sh")
        logger.info("3. .env 파일 생성")
        return False
    
    # 블러 모듈 확인 (선택사항)
    blur_module_path = os.getenv('BLUR_MODULE_PATH')
    if blur_module_path and not os.path.exists(blur_module_path):
        logger.warning(f"⚠️  블러 모듈을 찾을 수 없습니다: {blur_module_path}")
        logger.info("기본 블러를 사용합니다")
    
    # 출력 경로 확인
    temp_output_path = os.getenv('TEMP_OUTPUT_PATH', './output/temp/')
    final_output_path = os.getenv('FINAL_OUTPUT_PATH', '/mnt/raid5')
    try:
        os.makedirs(temp_output_path, exist_ok=True)
    except Exception as e:
        logger.error(f"❌ 임시 출력 경로 생성 실패: {temp_output_path} - {e}")
        return False
    
    logger.info("✅ 환경변수 검증 완료")
    return True

def main():
    """메인 실행 함수"""
    # 로깅 설정
    logger = setup_logging()
    
    logger.info("=" * 60)
    logger.info("🚀 RTSP Multithread Processor 시작")
    logger.info("=" * 60)
    
    try:
        # 환경변수 검증
        if not validate_environment():
            sys.exit(1)
        
        # 설정 로드
        from rtsp_multithread import RTSPProcessor, RTSPConfig
        
        rtsp_url = os.getenv('RTSP_URL')
        config = RTSPConfig.from_env(rtsp_url)
        
        # 설정 검증
        if not config.validate():
            logger.error("❌ 설정 검증 실패")
            sys.exit(1)
        
        # 현재 설정 출력
        logger.info("현재 설정:")
        logger.info(f"  📺 RTSP URL: {config.rtsp_url}")
        logger.info(f"  🚢 선박명: {config.overlay_config.vessel_name}")
        logger.info(f"  🔢 스트림 번호: {config.overlay_config.stream_number}")
        logger.info(f"  📁 임시 출력 경로: {config.temp_output_path}")
        logger.info(f"  📁 최종 출력 경로: {config.final_output_path}")
        logger.info(f"  🎯 해상도: {config.target_resolution[0]}x{config.target_resolution[1]}")
        logger.info(f"  🎬 FPS: {config.input_fps}")
        logger.info(f"  🌀 블러 활성화: {config.blur_enabled}")
        if config.blur_module_path:
            module_status = "✅ 존재" if os.path.exists(config.blur_module_path) else "❌ 없음"
            logger.info(f"  🤖 YOLO 모듈: {module_status}")
        logger.info(f"  📊 모니터링: {config.enable_monitoring}")
        
        # 프로세서 생성
        processor = RTSPProcessor(config)
        
        # 신호 처리 설정
        def signal_handler(signum, frame):
            signal_name = signal.Signals(signum).name
            logger.info(f"🛑 {signal_name} 신호 수신, 정상 종료 시작")
            processor.stop()
            logger.info("👋 프로그램 종료")
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
        signal.signal(signal.SIGTERM, signal_handler)  # terminate
        
        # 처리 시작
        logger.info("🎬 스트림 처리 시작...")
        processor.start()
        
        # 상태 모니터링 루프
        import time
        last_stats_time = 0
        stats_interval = 30  # 30초마다 상태 출력
        
        logger.info("📡 처리 중... (Ctrl+C로 중지)")
        
        while processor.is_running():
            try:
                current_time = time.time()
                
                # 주기적 상태 출력
                if current_time - last_stats_time >= stats_interval:
                    stats = processor.get_statistics()
                    
                    # 상태 정보
                    recv_frames = stats.get('stream_receiver', {}).get('received_frames', 0)
                    proc_frames = stats.get('frame_processor', {}).get('processed_frames', 0)
                    saved_frames = stats.get('frame_processor', {}).get('saved_frames', 0)
                    queue_size = stats.get('queue_status', {}).get('queue_size', 0)
                    
                    # 시스템 리소스
                    sys_stats = stats.get('system_stats', {})
                    cpu_percent = sys_stats.get('cpu_percent', 0)
                    memory_percent = sys_stats.get('memory_percent', 0)
                    
                    logger.info(f"📊 상태 - 수신:{recv_frames} 처리:{proc_frames} 저장:{saved_frames} 큐:{queue_size}")
                    logger.info(f"🖥️  리소스 - CPU:{cpu_percent:.1f}% 메모리:{memory_percent:.1f}%")
                    
                    last_stats_time = current_time
                
                # 최대 시간 체크
                if config.max_duration_seconds:
                    elapsed = time.time() - processor.start_time
                    if elapsed >= config.max_duration_seconds:
                        logger.info("⏰ 최대 처리 시간 도달, 자동 종료")
                        break
                
                time.sleep(1)
                
            except KeyboardInterrupt:
                logger.info("⌨️  키보드 인터럽트")
                break
            except Exception as e:
                logger.error(f"❌ 메인 루프 오류: {e}")
                time.sleep(5)  # 5초 대기 후 재시도
        
        # 정상 종료
        logger.info("🛑 처리 중지 중...")
        processor.stop()
        logger.info("✅ 정상 종료 완료")
        
    except KeyboardInterrupt:
        logger.info("⌨️  키보드 인터럽트로 종료")
    except ImportError as e:
        logger.error(f"❌ 모듈 import 오류: {e}")
        logger.info("필요한 패키지를 설치했는지 확인하세요:")
        logger.info("pip install opencv-python numpy psutil python-dotenv")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ 예상치 못한 오류: {e}")
        import traceback
        logger.error(f"상세 오류: {traceback.format_exc()}")
        sys.exit(1)

if __name__ == "__main__":
    main() 