#!/usr/bin/env python3
"""
RTSP 프로세서 모듈 테스트 스크립트

SharedPoolRTSPProcessor 클래스가 올바르게 모듈화되었는지 확인하는 테스트입니다.
"""

import os
import sys
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_imports():
    """모듈 임포트 테스트"""
    try:
        logger.info("모듈 임포트 테스트 시작...")
        
        # 각 모듈을 개별적으로 임포트하여 테스트
        from .config import RTSPConfig
        logger.info("✅ RTSPConfig 임포트 성공")
        
        from .statistics import FrameCounter, ResourceMonitor, PerformanceProfiler
        logger.info("✅ 통계 클래스들 임포트 성공")
        
        from .workers import rtsp_capture_process, blur_worker_process, save_worker_process
        logger.info("✅ 워커 함수들 임포트 성공")
        
        from .processor import SharedPoolRTSPProcessor
        logger.info("✅ SharedPoolRTSPProcessor 임포트 성공")
        
        logger.info("모든 모듈 임포트 성공!")
        return True
        
    except Exception as e:
        logger.error(f"모듈 임포트 실패: {e}")
        return False

def test_processor_initialization():
    """프로세서 초기화 테스트"""
    try:
        logger.info("프로세서 초기화 테스트 시작...")
        
        from .config import RTSPConfig
        from .processor import SharedPoolRTSPProcessor
        
        # 테스트용 설정 생성
        config = RTSPConfig(
            sources=["./test_video.mp4"],
            thread_count=2,
            blur_workers=1,
            save_workers=1,
            save_enabled=False,  # 테스트에서는 저장 비활성화
            preview_enabled=False  # 테스트에서는 미리보기 비활성화
        )
        
        # 프로세서 초기화
        processor = SharedPoolRTSPProcessor(config)
        logger.info("✅ SharedPoolRTSPProcessor 초기화 성공")
        
        # 기본 속성 확인
        assert processor.config == config
        assert processor.running == False
        assert len(processor.capture_processes) == 0
        assert len(processor.blur_processes) == 0
        assert len(processor.save_processes) == 0
        
        logger.info("✅ 프로세서 초기화 검증 성공")
        
        # 소스 할당 테스트
        source = processor.get_source_for_thread(0)
        assert source == "./test_video.mp4"
        logger.info("✅ 소스 할당 테스트 성공")
        
        # RTSP 소스 확인 테스트
        assert processor.is_rtsp_source("rtsp://example.com/stream") == True
        assert processor.is_rtsp_source("./test_video.mp4") == False
        logger.info("✅ RTSP 소스 확인 테스트 성공")
        
        logger.info("프로세서 초기화 테스트 완료!")
        return True
        
    except Exception as e:
        logger.error(f"프로세서 초기화 테스트 실패: {e}")
        return False

def main():
    """메인 테스트 함수"""
    logger.info("RTSP 프로세서 모듈 테스트 시작")
    logger.info("=" * 50)
    
    # 테스트 실행
    tests = [
        ("모듈 임포트", test_imports),
        ("프로세서 초기화", test_processor_initialization),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        logger.info(f"\n[테스트] {test_name}")
        logger.info("-" * 30)
        
        try:
            if test_func():
                logger.info(f"✅ {test_name} 테스트 통과")
                passed += 1
            else:
                logger.error(f"❌ {test_name} 테스트 실패")
                failed += 1
        except Exception as e:
            logger.error(f"❌ {test_name} 테스트 오류: {e}")
            failed += 1
    
    # 결과 출력
    logger.info("\n" + "=" * 50)
    logger.info("테스트 결과 요약")
    logger.info("=" * 50)
    logger.info(f"통과: {passed}")
    logger.info(f"실패: {failed}")
    logger.info(f"전체: {passed + failed}")
    
    if failed == 0:
        logger.info("🎉 모든 테스트가 성공적으로 통과했습니다!")
        return True
    else:
        logger.error(f"❌ {failed}개의 테스트가 실패했습니다.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)