#!/usr/bin/env python3
"""
블랙박스 API 테스트 스크립트
블랙박스 데이터 조회 및 카메라 영상 정보 전송 테스트
"""

import logging
import time
from datetime import datetime, timedelta
from api_client import BlackboxAPIClient, create_camera_video_data

def test_blackbox_api():
    """블랙박스 API 테스트"""
    print("=" * 60)
    print("🔍 블랙박스 API 테스트 시작")
    print("=" * 60)
    
    client = BlackboxAPIClient(base_url="http://localhost", timeout=10)
    
    # 연결 테스트
    print("📡 API 연결 테스트...")
    if client.test_connection():
        print("✅ API 연결 성공")
    else:
        print("❌ API 연결 실패")
        return
    
    # 블랙박스 데이터 조회 테스트
    print("\n📊 블랙박스 데이터 조회 테스트...")
    
    for i in range(5):
        print(f"\n--- 시도 {i+1}/5 ---")
        data = client.get_latest_gps()
        
        if data:
            print(f"✅ 데이터 수신 성공:")
            print(f"   🚢 선박 ID: {data.vessel_id}")
            print(f"   🚢 선박명: {data.vessel_name}")
            print(f"   🎣 어구 코드: {data.gear_code}")
            print(f"   🎣 어구명(한글): {data.gear_name_ko}")
            print(f"   📍 위도: {data.latitude}")
            print(f"   📍 경도: {data.longitude}")
            print(f"   🏃 속도: {data.speed} knots")
            print(f"   📐 Roll: {data.roll}°")
            print(f"   📐 Pitch: {data.pitch}°")
            print(f"   🌡️  온도: {data.temperature}°C")
            print(f"   📊 상태: {data.status}")
            print(f"   🥅 양투망 상태: {data.net_opt}")
            print(f"   ⏰ 기록 시간: {data.recorded_date}")
            
            # 속도 기반 녹화 조건 확인
            if data.speed is not None:
                if data.speed <= 10:
                    print(f"   🎬 녹화 조건: ✅ 만족 (속도 {data.speed} ≤ 10)")
                else:
                    print(f"   🎬 녹화 조건: ❌ 불만족 (속도 {data.speed} > 10)")
            else:
                print(f"   🎬 녹화 조건: ⚠️  속도 정보 없음")
        else:
            print("❌ 데이터 수신 실패")
        
        time.sleep(2)

def test_camera_video_api():
    """카메라 영상 정보 전송 API 테스트"""
    print("\n" + "=" * 60)
    print("📹 카메라 영상 정보 전송 API 테스트")
    print("=" * 60)
    
    client = BlackboxAPIClient(base_url="http://localhost", timeout=10)
    
    # 테스트용 영상 데이터 생성
    now = datetime.now()
    start_time = now - timedelta(minutes=5)
    end_time = now
    
    # 블랙박스 데이터 조회 (최신 정보로 영상 정보 생성)
    print("📊 최신 블랙박스 데이터 조회...")
    blackbox_data = client.get_latest_gps()
    
    if blackbox_data:
        print(f"✅ 블랙박스 데이터 수신: {blackbox_data.vessel_name}")
    else:
        print("⚠️  블랙박스 데이터 없음, 기본값 사용")
    
    # 테스트용 파일 경로 (실제로는 저장된 영상 파일)
    test_file_path = "/data/camera_video/vesselTest_stream01_241212_143052.mp4"
    test_file_name = "vesselTest_stream01_241212_143052.mp4"
    
    print(f"\n📁 테스트 파일 정보:")
    print(f"   경로: {test_file_path}")
    print(f"   이름: {test_file_name}")
    print(f"   시작시간: {start_time}")
    print(f"   종료시간: {end_time}")
    
    # 영상 데이터 객체 생성
    video_data = create_camera_video_data(
        file_path=test_file_path,
        file_name=test_file_name,
        record_start_time=start_time,
        record_end_time=end_time,
        blackbox_data=blackbox_data
    )
    
    print(f"\n📋 생성된 영상 정보:")
    print(f"   카메라 ID: {video_data.camera_id}")
    print(f"   카메라명: {video_data.camera_name}")
    print(f"   선박 ID: {video_data.vessel_id}")
    print(f"   선박명: {video_data.vessel_name}")
    print(f"   어구 코드: {video_data.gear_code}")
    print(f"   어구명: {video_data.gear_name_ko}")
    print(f"   파일명: {video_data.file_name}")
    print(f"   파일 크기: {video_data.file_size} bytes")
    print(f"   파일 확장자: {video_data.file_ext}")
    
    # API 전송 테스트
    print(f"\n📤 영상 정보 전송 중...")
    success = client.send_camera_video_info(video_data)
    
    if success:
        print("✅ 영상 정보 전송 성공!")
    else:
        print("❌ 영상 정보 전송 실패!")
    
    return success

def test_continuous_monitoring():
    """지속적인 모니터링 테스트 (1초마다)"""
    print("\n" + "=" * 60)
    print("🔄 지속적인 블랙박스 모니터링 테스트 (10초간)")
    print("=" * 60)
    
    client = BlackboxAPIClient(base_url="http://localhost", timeout=5)
    
    print("⏰ 1초마다 블랙박스 데이터 조회...")
    print("🛑 Ctrl+C로 중단 가능")
    
    try:
        for i in range(10):  # 10초간 테스트
            print(f"\n--- {i+1}/10 초 ---")
            
            data = client.get_latest_gps()
            
            if data:
                # 핵심 정보만 출력
                vessel = data.vessel_name or "Unknown"
                speed = data.speed or 0.0
                lat = data.latitude or 0.0
                lon = data.longitude or 0.0
                status = data.status or "Unknown"
                
                print(f"🚢 {vessel} | 🏃 {speed}kts | 📍 {lat:.4f},{lon:.4f} | 📊 {status}")
                
                # 녹화 조건 체크
                if speed <= 5:
                    print(f"   ✅ 녹화 진행 (속도: {speed} ≤ 5)")
                else:
                    print(f"   ⏸️  녹화 중단 (속도: {speed} > 5)")
            else:
                print("❌ 데이터 없음")
            
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n\n🛑 사용자에 의해 중단됨")

def main():
    """메인 테스트 함수"""
    # 로깅 설정
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print("🧪 블랙박스 API 통합 테스트 시작")
    print("=" * 60)
    
    try:
        # 1. 블랙박스 API 테스트
        test_blackbox_api()
        
        # 2. 카메라 영상 API 테스트
        video_success = test_camera_video_api()
        
        # 3. 지속적인 모니터링 테스트
        test_continuous_monitoring()
        
        print("\n" + "=" * 60)
        print("📊 테스트 결과 요약")
        print("=" * 60)
        print("✅ 블랙박스 데이터 조회: 완료")
        print(f"{'✅' if video_success else '❌'} 영상 정보 전송: {'성공' if video_success else '실패'}")
        print("✅ 지속적인 모니터링: 완료")
        
        if video_success:
            print("\n🎉 모든 테스트가 성공적으로 완료되었습니다!")
        else:
            print("\n⚠️  일부 테스트에서 문제가 발생했습니다.")
        
    except Exception as e:
        print(f"\n❌ 테스트 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 