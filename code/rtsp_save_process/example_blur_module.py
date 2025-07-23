"""
예제 블러 모듈
- 기존 HeadBlurrer 클래스와 호환
- 얼굴 검출 및 블러 처리 기능
"""

import cv2
import numpy as np
import logging

logger = logging.getLogger(__name__)

class HeadBlurrer:
    """얼굴 검출 및 블러 처리 클래스"""
    
    def __init__(self, num_camera=1):
        self.num_camera = num_camera
        self.face_cascade = None
        self.blur_strength = 51  # 블러 강도 (홀수)
        self.detection_scale = 1.1
        self.min_neighbors = 5
        self.min_size = (30, 30)
        
        # 얼굴 검출기 초기화
        self.init_face_detector()
        
        logger.info(f"HeadBlurrer 초기화 완료 (카메라 수: {num_camera})")
    
    def init_face_detector(self):
        """얼굴 검출기 초기화"""
        try:
            # OpenCV 내장 Haar Cascade 사용
            cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            self.face_cascade = cv2.CascadeClassifier(cascade_path)
            
            if self.face_cascade.empty():
                logger.warning("얼굴 검출기 로드 실패, 기본 블러 사용")
                self.face_cascade = None
            else:
                logger.info("얼굴 검출기 로드 성공")
                
        except Exception as e:
            logger.error(f"얼굴 검출기 초기화 오류: {e}")
            self.face_cascade = None
    
    def detect_faces(self, frame):
        """얼굴 검출"""
        try:
            if self.face_cascade is None:
                return []
            
            # 그레이스케일 변환
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # 얼굴 검출
            faces = self.face_cascade.detectMultiScale(
                gray,
                scaleFactor=self.detection_scale,
                minNeighbors=self.min_neighbors,
                minSize=self.min_size
            )
            
            return faces
            
        except Exception as e:
            logger.error(f"얼굴 검출 오류: {e}")
            return []
    
    def apply_blur_to_face(self, frame, x, y, w, h):
        """특정 얼굴 영역에 블러 적용"""
        try:
            # 얼굴 영역 추출
            face_roi = frame[y:y+h, x:x+w]
            
            # 블러 적용
            blurred_face = cv2.GaussianBlur(face_roi, (self.blur_strength, self.blur_strength), 0)
            
            # 원본 프레임에 블러된 얼굴 적용
            frame[y:y+h, x:x+w] = blurred_face
            
            return frame
            
        except Exception as e:
            logger.error(f"얼굴 블러 적용 오류: {e}")
            return frame
    
    def apply_full_blur(self, frame):
        """전체 프레임에 블러 적용"""
        try:
            return cv2.GaussianBlur(frame, (self.blur_strength, self.blur_strength), 0)
        except Exception as e:
            logger.error(f"전체 블러 적용 오류: {e}")
            return frame
    
    def process_frame(self, frame, camera_index=0):
        """프레임 처리 (메인 함수)"""
        try:
            if frame is None or frame.size == 0:
                logger.warning("빈 프레임 받음")
                return frame
            
            # 얼굴 검출
            faces = self.detect_faces(frame)
            
            if len(faces) > 0:
                # 검출된 얼굴에 블러 적용
                for (x, y, w, h) in faces:
                    frame = self.apply_blur_to_face(frame, x, y, w, h)
                
                logger.debug(f"얼굴 {len(faces)}개 검출 및 블러 적용")
            else:
                # 얼굴이 검출되지 않으면 전체 블러 적용
                frame = self.apply_full_blur(frame)
                logger.debug("얼굴 미검출, 전체 블러 적용")
            
            return frame
            
        except Exception as e:
            logger.error(f"프레임 처리 오류: {e}")
            # 오류 발생 시 기본 블러 적용
            return self.apply_full_blur(frame)
    
    def set_blur_strength(self, strength):
        """블러 강도 설정"""
        # 홀수로 맞춤
        if strength % 2 == 0:
            strength += 1
        
        self.blur_strength = max(3, min(strength, 101))  # 3~101 범위
        logger.info(f"블러 강도 설정: {self.blur_strength}")
    
    def set_detection_params(self, scale=1.1, min_neighbors=5, min_size=(30, 30)):
        """검출 파라미터 설정"""
        self.detection_scale = scale
        self.min_neighbors = min_neighbors
        self.min_size = min_size
        logger.info(f"검출 파라미터 설정: scale={scale}, neighbors={min_neighbors}, size={min_size}")

# 함수 기반 인터페이스도 제공
def apply_blur(frame, thread_id=0):
    """함수 기반 블러 적용 인터페이스"""
    try:
        # 전역 블러러 인스턴스 생성 (스레드별)
        global_blurrers = getattr(apply_blur, 'blurrers', {})
        
        if thread_id not in global_blurrers:
            global_blurrers[thread_id] = HeadBlurrer()
            apply_blur.blurrers = global_blurrers
        
        return global_blurrers[thread_id].process_frame(frame)
        
    except Exception as e:
        logger.error(f"apply_blur 함수 오류: {e}")
        # 폴백: 기본 블러
        return cv2.GaussianBlur(frame, (15, 15), 0)

# 테스트 함수
def test_blur_module():
    """블러 모듈 테스트"""
    logger.info("블러 모듈 테스트 시작")
    
    try:
        # HeadBlurrer 인스턴스 생성
        blurrer = HeadBlurrer()
        
        # 테스트 이미지 생성 (흰색 배경)
        test_frame = np.ones((480, 640, 3), dtype=np.uint8) * 255
        
        # 가짜 얼굴 영역 그리기 (검은 사각형)
        cv2.rectangle(test_frame, (200, 150), (400, 350), (0, 0, 0), -1)
        
        # 블러 처리
        blurred_frame = blurrer.process_frame(test_frame)
        
        if blurred_frame is not None:
            logger.info("블러 처리 테스트 성공")
            
            # 테스트 이미지 저장
            cv2.imwrite("test_blur_result.jpg", blurred_frame)
            logger.info("테스트 결과 저장: test_blur_result.jpg")
            
            return True
        else:
            logger.error("블러 처리 테스트 실패")
            return False
            
    except Exception as e:
        logger.error(f"블러 모듈 테스트 오류: {e}")
        return False

if __name__ == "__main__":
    # 테스트 실행
    logging.basicConfig(level=logging.INFO)
    success = test_blur_module()
    
    if success:
        print("✅ 블러 모듈 테스트 성공")
    else:
        print("❌ 블러 모듈 테스트 실패")