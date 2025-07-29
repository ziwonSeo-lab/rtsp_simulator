#!/usr/bin/env python3
"""
SharedPoolRTSPProcessor 클래스 추출 검증 스크립트

이 스크립트는 SharedPoolRTSPProcessor 클래스가 성공적으로 별도 모듈로 분리되었는지 확인합니다.
"""

import os
import sys
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_processor_import():
    """프로세서 모듈 임포트 테스트"""
    try:
        logger.info("SharedPoolRTSPProcessor 임포트 테스트...")
        
        # 모듈 경로 추가
        current_dir = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, current_dir)
        
        # 프로세서 모듈 임포트
        from rtsp_client_module.processor import SharedPoolRTSPProcessor
        from rtsp_client_module.config import RTSPConfig
        
        logger.info("✅ 모듈 임포트 성공")
        
        # 간단한 설정으로 프로세서 생성 테스트
        config = RTSPConfig(
            sources=["test_source.mp4"],
            thread_count=1,
            blur_workers=1,
            save_workers=1,
            save_enabled=False
        )
        
        processor = SharedPoolRTSPProcessor(config)
        logger.info("✅ 프로세서 인스턴스 생성 성공")
        
        # 기본 메소드 테스트
        source = processor.get_source_for_thread(0)
        assert source == "test_source.mp4"
        logger.info("✅ get_source_for_thread 메소드 작동 확인")
        
        # RTSP 소스 확인 테스트
        assert processor.is_rtsp_source("rtsp://example.com/stream") == True
        assert processor.is_rtsp_source("test_source.mp4") == False
        logger.info("✅ is_rtsp_source 메소드 작동 확인")
        
        # 소스 이름 추출 테스트
        name = processor.extract_source_name("test_source.mp4")
        assert name == "test_source.mp4"
        logger.info("✅ extract_source_name 메소드 작동 확인")
        
        logger.info("🎉 모든 기본 기능 테스트 통과!")
        return True
        
    except Exception as e:
        logger.error(f"❌ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_gui_import():
    """GUI 파일에서 프로세서 임포트 테스트"""
    try:
        logger.info("GUI 파일에서 프로세서 임포트 테스트...")
        
        # GUI 모듈 경로 추가
        current_dir = os.path.dirname(os.path.abspath(__file__))
        gui_path = os.path.join(current_dir, 'rtsp_gui')
        sys.path.insert(0, gui_path)
        
        # GUI 파일에서 프로세서 임포트가 제대로 작동하는지 확인
        # 실제로는 GUI 파일을 임포트하지만, 여기서는 임포트 구문만 확인
        gui_file = os.path.join(gui_path, 'multi-process_rtsp.py')
        
        if os.path.exists(gui_file):
            with open(gui_file, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # 임포트 구문 확인
            if 'from rtsp_client_module.processor import SharedPoolRTSPProcessor' in content:
                logger.info("✅ GUI 파일에 올바른 임포트 구문 확인")
            else:
                logger.error("❌ GUI 파일에 임포트 구문이 없습니다")
                return False
                
            # 기존 클래스 정의가 제거되었는지 확인
            if 'class SharedPoolRTSPProcessor:' not in content:
                logger.info("✅ 기존 클래스 정의가 성공적으로 제거됨")
            else:
                logger.error("❌ 기존 클래스 정의가 여전히 존재합니다")
                return False
                
            logger.info("🎉 GUI 파일 수정 확인 완료!")
            return True
        else:
            logger.error(f"❌ GUI 파일을 찾을 수 없습니다: {gui_file}")
            return False
            
    except Exception as e:
        logger.error(f"❌ GUI 테스트 실패: {e}")
        return False

def main():
    """메인 테스트 함수"""
    logger.info("SharedPoolRTSPProcessor 추출 검증 시작")
    logger.info("=" * 60)
    
    tests = [
        ("프로세서 모듈 임포트", test_processor_import),
        ("GUI 파일 수정 확인", test_gui_import),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        logger.info(f"\n[테스트] {test_name}")
        logger.info("-" * 40)
        
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
    
    # 결과 요약
    logger.info("\n" + "=" * 60)
    logger.info("검증 결과 요약")
    logger.info("=" * 60)
    logger.info(f"통과: {passed}")
    logger.info(f"실패: {failed}")
    logger.info(f"전체: {passed + failed}")
    
    if failed == 0:
        logger.info("🎉 SharedPoolRTSPProcessor 클래스 추출이 성공적으로 완료되었습니다!")
        logger.info("\n다음 작업이 완료되었습니다:")
        logger.info("1. SharedPoolRTSPProcessor 클래스를 processor.py 모듈로 분리")
        logger.info("2. 필요한 의존성을 올바른 모듈에서 임포트하도록 설정")
        logger.info("3. 기존 GUI 파일에서 클래스 정의 제거 및 임포트 구문 추가")
        logger.info("4. 워커 함수들을 workers.py 모듈에서 임포트하도록 설정")
        return True
    else:
        logger.error(f"❌ {failed}개의 검증 테스트가 실패했습니다.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)