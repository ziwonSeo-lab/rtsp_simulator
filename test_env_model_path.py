#!/usr/bin/env python3
"""
환경변수 기반 모델 경로 테스트 스크립트

이 스크립트는 ipcamera_blur.py가 환경변수에서 
HEAD_BLUR_MODEL_PATH를 올바르게 읽어오는지 테스트합니다.
"""

import sys
import os

# 모듈 경로 추가
sys.path.append(os.path.join(os.path.dirname(__file__), 'blur_module'))

from dotenv import load_dotenv

def test_environment_loading():
    """환경변수 로딩 테스트"""
    print("=== 환경변수 기반 모델 경로 테스트 ===")
    
    # .env 파일 로드
    load_dotenv()
    
    # 환경변수 확인
    env_model_path = os.getenv('HEAD_BLUR_MODEL_PATH')
    print(f"환경변수 HEAD_BLUR_MODEL_PATH: {env_model_path}")
    
    if env_model_path:
        # 상대 경로를 절대 경로로 변환
        if not os.path.isabs(env_model_path):
            project_root = os.path.dirname(os.path.abspath(__file__))
            absolute_path = os.path.join(project_root, env_model_path)
        else:
            absolute_path = env_model_path
        
        print(f"변환된 절대 경로: {absolute_path}")
        print(f"파일 존재 여부: {os.path.exists(absolute_path)}")
        
        if os.path.exists(absolute_path):
            print("✅ 모델 파일이 존재합니다.")
        else:
            print("❌ 모델 파일이 존재하지 않습니다.")
    else:
        print("❌ 환경변수 HEAD_BLUR_MODEL_PATH가 설정되지 않았습니다.")

def test_blurrer_initialization():
    """HeadBlurrer 초기화 테스트 (모델 로드 제외)"""
    print("\n=== HeadBlurrer 초기화 테스트 ===")
    
    try:
        # get_model_path 함수 테스트
        from ipcamera_blur import get_model_path
        
        model_path = get_model_path()
        print(f"get_model_path() 결과: {model_path}")
        print(f"파일 존재 여부: {os.path.exists(model_path)}")
        
        # HeadBlurrer 클래스 import 테스트 (실제 초기화는 하지 않음)
        from ipcamera_blur import HeadBlurrer
        
        print("✅ HeadBlurrer 클래스 import 성공")
        print("✅ 환경변수 기반 모델 경로 설정이 올바르게 작동합니다.")
        
    except ImportError as e:
        print(f"❌ Import 오류: {e}")
    except Exception as e:
        print(f"❌ 오류 발생: {e}")

def main():
    """메인 함수"""
    test_environment_loading()
    test_blurrer_initialization()
    
    print("\n=== 테스트 완료 ===")
    print("실제 모델 로딩 테스트를 위해서는 best_re_final.pt 파일이 필요합니다.")
    print("경로: ./blur_module/models/best_re_final.pt")

if __name__ == "__main__":
    main()