import cv2
import time
from datetime import datetime
import os
import argparse
from ultralytics import YOLO
import numpy as np

class HeadBlurrer:
    def __init__(self, model_path="best_re_final.engine", num_camera=1):
        """
        HeadBlurrer 초기화
        
        Args:
            model_path (str): PyTorch 모델 파일 경로
        """
        self.model_path = model_path
        self.conf_threshold = 0.5  # 탐지 신뢰도 임계값
        
        # 모델 로드
        self.model = self._load_model()
        print(f"✅ 모델 로드 완료: {model_path}")
        
        self.frame_counts = [0 for i in range(num_camera)]
        self.last_head_boxes = [[] for i in range(num_camera)]
    
    def _load_model(self):
        """PyTorch YOLO 모델 로드"""
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"모델 파일을 찾을 수 없습니다: {self.model_path}")
        
        try:
            model = YOLO(self.model_path)
            return model
        except Exception as e:
            raise RuntimeError(f"모델 로드 실패: {e}")
            
    def _detect_heads(self, image):
        """
        머리 탐지 수행
        

        Args:
            image: OpenCV 이미지 (BGR)
        
        Returns:
            list: 머리 바운딩 박스 좌표 리스트 [[x1,y1,x2,y2], ...]
        """
        try:
            # YOLO 추론 
            results = self.model(image, conf=self.conf_threshold, verbose=False)
            
            head_boxes = []
            if results[0].boxes is not None:
                # 바운딩 박스 좌표 추출
                boxes = results[0].boxes.xyxy.cpu().numpy()  # [x1, y1, x2, y2] 형태
                for box in boxes:
                    x1, y1, x2, y2 = box.astype(int)
                    head_boxes.append([x1, y1, x2, y2])
            else:
                print("탐지된 머리 없음")
            
            return head_boxes
            
        except Exception as e:
            print(f"⚠️  머리 탐지 중 오류: {e}")
            return []
    
    def _apply_blur_to_heads(self, image, head_boxes, blur_strength=0.01):
        """
        머리 영역에 블러 효과 적용
        
        Args:
            image: 원본 이미지
            head_boxes: 머리 바운딩 박스 리스트
        
        Returns:
            블러 처리된 이미지
        """
        result_image = image.copy()
        
        for box in head_boxes:
            x1, y1, x2, y2 = box
            
            # 좌표 범위 검증
            h, w = image.shape[:2]
            x1 = max(0, min(x1, w-1))
            y1 = max(0, min(y1, h-1))
            x2 = max(x1+1, min(x2, w))
            y2 = max(y1+1, min(y2, h))
            
            # 머리 영역 추출
            head_region = result_image[y1:y2, x1:x2]
            
            if head_region.size > 0:
                hh, ww = head_region.shape[:2]
                sw = max(1, int(ww * blur_strength))
                sh = max(1, int(hh * blur_strength))
                # 초고속 블러 (축소 후 확대)
                small = cv2.resize(head_region, (sw, sh), interpolation=cv2.INTER_LINEAR)
                blurred = cv2.resize(small, (ww, hh), interpolation=cv2.INTER_NEAREST)

                result_image[y1:y2, x1:x2] = blurred
        
        return result_image

    def process_frame(self, frame, index_camera, frame_interval=1, blur_strength=0.01):
        """
        n 프레임마다 탐지 수행, 그 외에는 이전 탐지 결과 사용
        """

        if index_camera >= len(self.frame_counts):
            extra = index_camera - len(self.frame_counts) + 1
            self.frame_counts.extend([0 for _ in range(extra)])
            self.last_head_boxes.extend([] for _ in range(extra))
        
        if self.frame_counts[index_camera] % frame_interval == 0:
            self.last_head_boxes[index_camera] = self._detect_heads(frame)
            
        self.frame_counts[index_camera] += 1

        blurred_frame = self._apply_blur_to_heads(frame, self.last_head_boxes[index_camera], blur_strength)
        return blurred_frame

def main():
    parser = argparse.ArgumentParser(description="IP 카메라 스트림 블러 처리")
    parser.add_argument(
        "-i", "--interval", type=int, default=3,
        help="머리 탐지를 수행할 프레임 간격 (기본값: 3)"
    )
    parser.add_argument(
        "-s", "--save", action="store_true",
        help="실행 중 전체 영상을 저장 (원본 및 블러 처리 영상)"
    )
    parser.add_argument(
        "--save-original", action="store_true",
        help="원본 영상만 저장"
    )
    parser.add_argument(
        "--save-blurred", action="store_true",
        help="블러 처리 영상만 저장"
    )

    parser.add_argument(
        "-c", "--confidence", type=float, default=0.3,
        help="머리 탐지 신뢰도 임계값 (기본값: 0.3)"
    )
    parser.add_argument(
        "-f", "--fps", type=float, default=15.0,
        help="비디오 FPS (기본값: 15.0)"
    )

    args = parser.parse_args()
    
    # 환경변수에서 설정 읽기
    interval = args.interval
    
    model_path = 'best_re_final.engine'
    confidence_threshold = args.confidence
    rtsp_url_1 = 'rtsp://root:root@192.168.1.101:554/cam0_0'
    rtsp_url_2 = 'rtsp://root:root@192.168.1.102:554/cam0_1'
    
    # 비디오/카메라 설정
    video_fps = args.fps
    video_codec = 'mp4v'
    output_dir = 'output'
    num_cameras = 2
    blur_strength = 0.01

    # 저장 설정 확인
    save_original = args.save or args.save_original
    save_blurred = args.save or args.save_blurred
    save_enabled = save_original or save_blurred

    # output 디렉토리 생성 (저장이 활성화된 경우)
    if save_enabled:
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            print(f"✅ 출력 디렉토리 생성: {output_dir}")

    print(f"🔧 설정:")
    print(f"   - 모델 경로: {model_path}")
    print(f"   - 신뢰도 임계값: {confidence_threshold}")
    print(f"   - 탐지 간격: {interval}프레임")
    print(f"   - 블러 강도: {blur_strength}")
    print(f"   - 카메라 개수: {num_cameras}")
    print(f"   - 비디오 FPS: {video_fps}")
    print(f"   - 비디오 코덱: {video_codec}")
    print(f"   - 출력 디렉토리: {output_dir}")
    print(f"   - 카메라 1: {rtsp_url_1}")
    print(f"   - 카메라 2: {rtsp_url_2}")
    print(f"   - 저장 모드: {'활성화' if save_enabled else '비활성화'}")
    if save_enabled:
        save_types = []
        if save_original:
            save_types.append("원본")
        if save_blurred:
            save_types.append("블러")
        print(f"   - 저장 타입: {', '.join(save_types)}")

    cap1 = cv2.VideoCapture(rtsp_url_1)
    cap2 = cv2.VideoCapture(rtsp_url_2)
    blurrer = HeadBlurrer(model_path=model_path, num_camera=num_cameras)
    blurrer.conf_threshold = confidence_threshold

    if not cap1.isOpened() or not cap2.isOpened():
        print("카메라 스트림을 열 수 없습니다.")
        return
        
    # 저장 관련 변수 초기화
    out1_original = None
    out2_original = None
    out1_blurred = None
    out2_blurred = None

    width1 = int(cap1.get(cv2.CAP_PROP_FRAME_WIDTH))
    height1 = int(cap1.get(cv2.CAP_PROP_FRAME_HEIGHT))
    width2 = int(cap2.get(cv2.CAP_PROP_FRAME_WIDTH))
    height2 = int(cap2.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fourcc = cv2.VideoWriter_fourcc(*video_codec)

    # 저장이 활성화된 경우 VideoWriter 설정
    if save_enabled:
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        print(f"📹 영상 저장 시작: {now}")
        
        if save_original:
            out1_original = cv2.VideoWriter(
                os.path.join(output_dir, f"cam1_original_{now}.mp4"), 
                fourcc, video_fps, (width1, height1)
            )
            out2_original = cv2.VideoWriter(
                os.path.join(output_dir, f"cam2_original_{now}.mp4"), 
                fourcc, video_fps, (width2, height2)
            )
            print(f"   - 원본 영상: cam1_original_{now}.mp4, cam2_original_{now}.mp4")
            
        if save_blurred:
            out1_blurred = cv2.VideoWriter(
                os.path.join(output_dir, f"cam1_blurred_{now}.mp4"), 
                fourcc, video_fps, (width1, height1)
            )
            out2_blurred = cv2.VideoWriter(
                os.path.join(output_dir, f"cam2_blurred_{now}.mp4"), 
                fourcc, video_fps, (width2, height2)
            )
            print(f"   - 블러 영상: cam1_blurred_{now}.mp4, cam2_blurred_{now}.mp4")

    while True:
        ret1, frame1 = cap1.read()
        ret2, frame2 = cap2.read()
        
        if not ret1 or not ret2:
            print("프레임을 읽을 수 없습니다.")
            break

        blurred_1 = blurrer.process_frame(frame1, index_camera=1, frame_interval=interval, blur_strength=blur_strength)
        blurred_2 = blurrer.process_frame(frame2, index_camera=2, frame_interval=interval, blur_strength=blur_strength)
        cv2.imshow("IP Camera Stream 1", blurred_1)
        cv2.imshow("IP Camera Stream 2", blurred_2)
        
        # 저장이 활성화된 경우 프레임 저장
        if save_enabled:
            if save_original and out1_original and out2_original:
                out1_original.write(frame1)
                out2_original.write(frame2)
            
            if save_blurred and out1_blurred and out2_blurred:
                out1_blurred.write(blurred_1)
                out2_blurred.write(blurred_2)
        
        key = cv2.waitKey(1) & 0xFF
        # 'q' 키로 종료
        if key == ord('q'):
            print("🔴 종료 신호 수신")
            break

    # 리소스 해제
    print("🔄 리소스 정리 중...")
    cap1.release()
    cap2.release()
    
    # VideoWriter 해제 및 저장 완료 메시지
    if save_enabled:
        saved_files = []
        if out1_original:
            out1_original.release()
            saved_files.extend([f"cam1_original_{now}.mp4", f"cam2_original_{now}.mp4"])
        if out2_original:
            out2_original.release()
        if out1_blurred:
            out1_blurred.release()
            saved_files.extend([f"cam1_blurred_{now}.mp4", f"cam2_blurred_{now}.mp4"])
        if out2_blurred:
            out2_blurred.release()
        
        print(f"✅ 영상 저장 완료:")
        for file in saved_files:
            print(f"   - {os.path.join(output_dir, file)}")
    
    cv2.destroyAllWindows()
    print("🏁 프로그램 종료")

if __name__ == "__main__":
    main()

# ─────────────────────────────────────────────────────────────
# rtsp_simulator_ffmpeg.py가 동적 로딩하는 apply_blur 래퍼
# ─────────────────────────────────────────────────────────────

_blurrer_cache = {"obj": None}   
       # 싱글턴 캐시
import threading
_blurrer = HeadBlurrer(model_path="best_re_final.engine", num_camera=16)
_thread2cam = {}  

def apply_blur(frame,
               index_camera: int = 1,
               frame_interval: int = 3,
               blur_strength: float = 0.01):

    tid = threading.get_ident()
    idx = _thread2cam.setdefault(tid, len(_thread2cam) + 1)  # 1‑base
    return _blurrer.process_frame(
        frame, index_camera=idx,
        frame_interval=frame_interval,
        blur_strength=blur_strength
    )