#!/usr/bin/env python3
"""
FPS 모니터링 디버그 스크립트

각 프로세스 단계별로 실시간 FPS를 모니터링하여 
어디서 문제가 발생하는지 파악합니다.

단계별 FPS 출력:
1. 📹 [CAPTURE] - RTSP 캡처 FPS
2. 🔍 [BLUR] - 블러 처리 FPS  
3. 💾 [SAVE] - 저장 처리 FPS (스트림별 상세)
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
    """로깅 설정 - FPS 모니터링에 최적화"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('debug_fps_monitoring.log')
        ]
    )

def create_debug_config():
    """디버그용 설정 생성"""
    config = RTSPConfig()
    
    # 2개 스트림으로 단순화하여 명확한 분석
    config.sources = [
        "rtsp://10.2.10.158:1111/live",
        "rtsp://10.2.10.158:1112/live"
    ]
    
    # 스레드 수 2개로 제한
    config.thread_count = 2
    
    # 2분 동안 모니터링 (수정사항 빠른 검증용)
    config.max_duration_seconds = 120
    config.save_interval_seconds = 20  # 20초마다 파일 분할 (수정사항 적용)
    
    # 워커 수 최소화하여 명확한 분석
    config.blur_workers = 2
    config.save_workers = 2
    
    # 출력 경로
    config.save_path = "./debug_fps_output"
    
    # FPS 설정
    config.input_fps = 15.0
    config.force_fps = True
    
    return config

def print_analysis_header():
    """분석 헤더 출력"""
    print("=" * 80)
    print("🔍 FPS 모니터링 디버그 분석")
    print("=" * 80)
    print()
    print("📋 분석 목표:")
    print("  1. 📹 [CAPTURE] - RTSP에서 받은 실제 FPS 확인")
    print("  2. 🔍 [BLUR] - 블러 처리 속도 확인")
    print("  3. 💾 [SAVE] - 저장 시 15fps 제어 효과 확인")
    print()
    print("🎯 예상 결과 (수정 후):")
    print("  - CAPTURE: 정확히 15fps (정밀 타이밍 제어)")
    print("  - BLUR: ~15fps (전체 처리량)")
    print("  - SAVE: 정확히 15fps (누적 오차 보정)")
    print("  - FILES: 120초 → 각 스트림당 6개 파일 (20초씩)")
    print()
    print("=" * 80)
    print()

def analyze_logs_realtime():
    """실시간 로그 분석"""
    print("📊 실시간 FPS 분석 시작...")
    print("다음 로그 패턴을 확인하세요:")
    print()
    print("  📹 [CAPTURE] Stream X: 실제 캡처 FPS = XX.X")
    print("  🔍 [BLUR] Worker X: 블러 처리 FPS = XX.X")
    print("  💾 [SAVE] Worker X: 전체 저장 FPS = XX.X, 스트림별 FPS = [stream_1:XX.X, stream_2:XX.X]")
    print()
    print("🚨 문제 진단 가이드:")
    print("  - CAPTURE FPS가 15fps보다 높으면 → 캡처 FPS 제어 문제")
    print("  - BLUR FPS가 CAPTURE보다 낮으면 → 블러 처리 병목")
    print("  - SAVE 스트림별 FPS가 15fps보다 높으면 → 저장 FPS 제어 실패")
    print()

def main():
    """메인 함수"""
    print_analysis_header()
    
    setup_logging()
    logger = logging.getLogger(__name__)
    
    config = create_debug_config()
    
    # 출력 디렉토리 생성
    os.makedirs(config.save_path, exist_ok=True)
    
    processor = None
    
    try:
        logger.info("🚀 FPS 디버그 모니터링 시작")
        logger.info(f"설정: {config.thread_count}스트림, {config.blur_workers}블러워커, {config.save_workers}저장워커")
        
        analyze_logs_realtime()
        
        processor = SharedPoolRTSPProcessor(config)
        processor.start()
        
        # 모니터링 실행
        start_time = time.time()
        
        while time.time() - start_time < config.max_duration_seconds:
            # 간단한 통계 출력 (로그에서 상세 FPS 확인)
            stats = processor.get_statistics()
            elapsed = time.time() - start_time
            
            if stats['saved_frames'] > 0:
                overall_fps = stats['saved_frames'] / elapsed
                print(f"\r⏱️  경과: {elapsed:.0f}초 | "
                      f"총 저장: {stats['saved_frames']}프레임 | "
                      f"전체 FPS: {overall_fps:.1f} | "
                      f"큐: B{stats['blur_queue_size']} S{stats['save_queue_size']}", end="")
            
            time.sleep(1)
        
        print("\n\n🏁 모니터링 완료 - 프로세서 종료 중...")
        
    except KeyboardInterrupt:
        print("\n\n⏹️  사용자 중단")
    except Exception as e:
        logger.error(f"모니터링 중 오류: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if processor:
            processor.stop()
        
        print("\n" + "=" * 80)
        print("📋 분석 완료 - 결과 확인")
        print("=" * 80)
        print()
        print("📄 상세 로그 파일: debug_fps_monitoring.log")
        print("📁 저장된 비디오: ./debug_fps_output/")
        print()
        print("🔍 로그에서 다음 패턴을 찾아 분석하세요:")
        print("  1. 📹 [CAPTURE] - '정밀 FPS 제어 시작' 및 실제 캡처 FPS")
        print("  2. 🔍 [BLUR] - 블러 워커별 처리 FPS")
        print("  3. 💾 [SAVE] - '정밀 15fps 제어 활성화' 및 저장 FPS")
        print("  4. 📁 [FILES] - '시간 기반 파일 분할' 메시지 확인")
        print()
        print("✅ 수정사항 적용 확인:")
        print("  - 각 스트림당 6개 파일 생성 (20초씩)")
        print("  - 각 파일이 정확히 20초, 15fps, 300프레임인지 확인")
        print("  - 타이밍 오차 보정 메시지 확인")
        print()
        print("🧪 추가 검증 명령어:")
        print("  python test_fps_fix.py  # 생성된 파일 상세 분석")

if __name__ == "__main__":
    main()