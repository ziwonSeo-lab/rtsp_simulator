#!/usr/bin/env python3
"""
Stream-Independent 15fps 제어 테스트 스크립트

이 스크립트는 새로 구현된 스트림별 독립적 15fps 제어가 
올바르게 작동하는지 테스트합니다.
"""

import sys
import os
import time
import logging

# 모듈 경로 추가
sys.path.append(os.path.join(os.path.dirname(__file__), 'code'))

from rtsp_client_module.config import RTSPConfig
from rtsp_client_module.processor import SharedPoolRTSPProcessor

def setup_logging():
    """로깅 설정"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('test_stream_independent_fps.log')
        ]
    )

def create_test_config():
    """테스트용 설정 생성"""
    config = RTSPConfig()
    
    # 2개의 테스트 소스 (동일한 소스 사용)
    config.sources = [
        "rtsp://10.2.10.158:1111/live",
        "rtsp://10.2.10.158:1112/live"
    ]
    
    # 스레드 수 2개로 제한
    config.thread_count = 2
    
    # 짧은 테스트를 위한 설정
    config.max_duration_seconds = 30  # 30초 테스트
    config.save_interval = 150  # 10초 분량 (15fps * 10초)
    
    # 블러 워커 줄이기
    config.blur_workers = 1
    config.save_workers = 2
    
    # 출력 경로
    config.save_path = "./test_output_stream_independent"
    
    # 로그 활성화
    config.input_fps = 15.0
    config.force_fps = True
    
    return config

def main():
    """메인 테스트 함수"""
    print("=== Stream-Independent 15fps 제어 테스트 시작 ===")
    
    setup_logging()
    logger = logging.getLogger(__name__)
    
    config = create_test_config()
    
    # 출력 디렉토리 생성
    os.makedirs(config.save_path, exist_ok=True)
    
    processor = None
    
    try:
        logger.info("RTSP 프로세서 초기화 중...")
        processor = SharedPoolRTSPProcessor(config)
        
        logger.info("스트림별 독립적 15fps 제어 테스트 시작")
        logger.info(f"테스트 소스: {config.sources}")
        logger.info(f"테스트 기간: {config.max_duration_seconds}초")
        logger.info(f"예상 결과: 각 스트림마다 15fps로 저장되어야 함")
        
        # 프로세서 시작
        processor.start()
        
        # 테스트 실행
        start_time = time.time()
        
        while time.time() - start_time < config.max_duration_seconds:
            # 통계 출력
            stats = processor.get_statistics()
            
            logger.info("=== 실시간 통계 ===")
            logger.info(f"수신 프레임: {stats['received_frames']}")
            logger.info(f"처리 프레임: {stats['processed_frames']}")
            logger.info(f"저장 프레임: {stats['saved_frames']}")
            logger.info(f"손실률: {stats['loss_rate']:.2f}%")
            logger.info(f"저장률: {stats['save_rate']:.2f}%")
            
            # 큐 상태
            logger.info(f"블러큐: {stats['blur_queue_size']}, 저장큐: {stats['save_queue_size']}")
            
            time.sleep(5)  # 5초마다 통계 출력
        
        logger.info("테스트 완료 - 프로세서 종료 중...")
        
    except KeyboardInterrupt:
        logger.info("사용자에 의해 테스트 중단됨")
    except Exception as e:
        logger.error(f"테스트 중 오류 발생: {e}")
    finally:
        if processor:
            processor.stop()
        
        # 최종 통계 출력
        if processor:
            final_stats = processor.get_statistics()
            print("\n=== 최종 테스트 결과 ===")
            print(f"총 수신 프레임: {final_stats['received_frames']}")
            print(f"총 처리 프레임: {final_stats['processed_frames']}")
            print(f"총 저장 프레임: {final_stats['saved_frames']}")
            print(f"최종 손실률: {final_stats['loss_rate']:.2f}%")
            print(f"최종 저장률: {final_stats['save_rate']:.2f}%")
        
        print(f"\n저장된 비디오 파일들을 확인하세요: {config.save_path}")
        print("각 스트림별로 독립적으로 15fps로 저장되었는지 확인하세요.")
        print("=== 테스트 종료 ===")

if __name__ == "__main__":
    main()