#!/usr/bin/env python3
"""
블랙박스 API 통합 테스트 스크립트
오버레이 텍스트에 블랙박스 데이터가 정상적으로 반영되는지 테스트
"""

import logging
import time
from datetime import datetime
import os
import sys

# dotenv 로드
try:
    from dotenv import load_dotenv
    load_dotenv('.env.stream1')  # 테스트용 env 파일 로드
    print("✅ 환경변수 로드 완료")
except ImportError:
    print("⚠️  python-dotenv 없음, 시스템 환경변수만 사용")

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import RTSPConfig
from blackbox_manager import BlackboxManager, OverlayData
from frame_processor import OverlayRenderer

def test_overlay_with_blackbox():
    """블랙박스 데이터와 오버레이 통합 테스트"""
    print("=" * 60)
    print("🧪 블랙박스 오버레이 통합 테스트")
    print("=" * 60)
    
    # 설정 로드
    config = RTSPConfig.from_env()
    
    print(f"📋 설정 정보:")
    print(f"  블랙박스 API: {config.blackbox_api_url}")
    print(f"  폴링 간격: {config.api_poll_interval}초")
    print(f"  속도 임계값: {config.recording_speed_threshold} knots")
    print(f"  기본 선박명: {config.overlay_config.vessel_name}")
    print(f"  기본 위치: {config.overlay_config.latitude}, {config.overlay_config.longitude}")
    
    # 블랙박스 매니저 생성
    blackbox_manager = BlackboxManager(config)
    
    # 오버레이 렌더러 생성
    overlay_renderer = OverlayRenderer(config)
    overlay_renderer.set_blackbox_manager(blackbox_manager)
    
    print(f"\n🚀 블랙박스 매니저 시작...")
    blackbox_manager.start()
    
    try:
        print(f"\n⏰ 15초간 오버레이 텍스트 변화 모니터링...")
        
        for i in range(15):
            print(f"\n--- {i+1}/15 초 ---")
            
            # 오버레이 텍스트 생성
            overlay_text = overlay_renderer.create_single_line_overlay()
            print(f"📺 오버레이: {overlay_text}")
            
            # 블랙박스 데이터 상태 확인
            blackbox_data = blackbox_manager.get_blackbox_data()
            overlay_data = blackbox_manager.get_overlay_data()
            
            if blackbox_data:
                print(f"📊 블랙박스: speed={blackbox_data.speed}, vessel={blackbox_data.vessel_name}")
                print(f"📍 위치: {blackbox_data.latitude}, {blackbox_data.longitude}")
                print(f"🎬 녹화 허용: {'✅' if blackbox_manager.is_recording_enabled() else '❌'}")
            else:
                print(f"❌ 블랙박스 데이터 없음")
            
            if overlay_data:
                print(f"🎨 오버레이 데이터: {overlay_data.vessel_name} @ {overlay_data.latitude},{overlay_data.longitude}")
            else:
                print(f"❌ 오버레이 데이터 없음")
            
            time.sleep(1)
    
    except KeyboardInterrupt:
        print(f"\n🛑 사용자에 의해 중단됨")
    
    finally:
        print(f"\n🔄 블랙박스 매니저 중지...")
        blackbox_manager.stop()
        
        # 최종 통계
        stats = blackbox_manager.get_statistics()
        print(f"\n📊 최종 통계:")
        for key, value in stats.items():
            print(f"  {key}: {value}")
    
    print(f"\n✅ 테스트 완료!")

def test_overlay_fallback():
    """블랙박스 API 없을 때 기본값 사용 테스트"""
    print("\n" + "=" * 60)
    print("🧪 오버레이 기본값 테스트 (API 없음)")
    print("=" * 60)
    
    # 잘못된 API URL로 설정
    config = RTSPConfig.from_env()
    config.blackbox_api_url = "http://nonexistent:9999"
    
    print(f"📋 설정: API URL = {config.blackbox_api_url} (존재하지 않음)")
    
    # 블랙박스 매니저 생성 (실패할 예정)
    blackbox_manager = BlackboxManager(config)
    
    # 오버레이 렌더러 생성
    overlay_renderer = OverlayRenderer(config)
    overlay_renderer.set_blackbox_manager(blackbox_manager)
    
    print(f"\n🚀 블랙박스 매니저 시작...")
    blackbox_manager.start()
    
    try:
        print(f"\n⏰ 5초간 기본값 오버레이 확인...")
        
        for i in range(5):
            print(f"\n--- {i+1}/5 초 ---")
            
            # 오버레이 텍스트 생성 (기본값 사용되어야 함)
            overlay_text = overlay_renderer.create_single_line_overlay()
            print(f"📺 오버레이: {overlay_text}")
            
            # 상태 확인
            print(f"📊 블랙박스 데이터: {'있음' if blackbox_manager.get_blackbox_data() else '없음'}")
            print(f"🎨 오버레이 데이터: {'있음' if blackbox_manager.get_overlay_data() else '없음'}")
            print(f"🎬 녹화 허용: {'✅' if blackbox_manager.is_recording_enabled() else '❌'}")
            
            time.sleep(1)
    
    finally:
        blackbox_manager.stop()
    
    print(f"\n✅ 기본값 테스트 완료!")

def main():
    """메인 테스트 함수"""
    # 로깅 설정
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print("🧪 블랙박스 오버레이 통합 테스트 시작")
    
    try:
        # 1. 정상 API 연동 테스트
        test_overlay_with_blackbox()
        
        # 2. API 실패 시 기본값 테스트  
        test_overlay_fallback()
        
        print("\n" + "=" * 60)
        print("🎉 모든 테스트 완료!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ 테스트 중 오류: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 