git # RTSP 시뮬레이터 v2 🎥

고성능 RTSP 스트림 및 비디오 파일 처리 시뮬레이터입니다. 스레드별 독립적인 YOLO/HeadBlurrer 인스턴스를 지원하며, 실시간 영상 처리와 다양한 비디오 코덱을 통한 고품질 영상 저장이 가능합니다.

## 📋 주요 기능

### 🎯 핵심 특징
- **멀티스레드 처리**: 최대 10개의 독립적인 스레드로 여러 RTSP 소스 동시 처리
- **스레드별 AI 모델**: 각 스레드마다 독립적인 YOLO/HeadBlurrer 인스턴스로 GPU 경합 해결
- **실시간 영상 처리**: 얼굴 블러링, 객체 탐지 등 커스텀 모듈 지원
- **고급 비디오 인코딩**: FFmpeg 기반 다양한 코덱 및 압축 옵션
- **실시간 모니터링**: CPU, RAM, GPU 사용률 및 성능 프로파일링
- **직관적 GUI**: 스크롤 가능한 설정 패널과 실시간 미리보기

### 🎬 지원 비디오 코덱
- **H.264 (libx264)**: 범용 호환성
- **H.265 (libx265)**: 고효율 압축
- **VP9 (libvpx-vp9)**: 웹 최적화
- **AV1 (libaom-av1)**: 차세대 압축
- **XVID, H.262**: 레거시 지원

### 📁 지원 컨테이너 포맷
- MP4, MKV, WebM, AVI

### ⚡ 하드웨어 가속 지원
- **NVIDIA CUDA**: h264_nvenc, hevc_nvenc
- **Intel Quick Sync**: QSV 가속
- **AMD AMF**: AMD 하드웨어 가속

## 🛠️ 시스템 요구사항

### 필수 요구사항
- **Python**: 3.7 이상
- **운영체제**: Windows, macOS, Linux
- **RAM**: 최소 4GB (8GB 권장)
- **CPU**: 멀티코어 프로세서 권장

### 선택적 요구사항
- **GPU**: NVIDIA/AMD/Intel GPU (하드웨어 가속용)
- **FFmpeg**: 고급 비디오 인코딩용 (설치 필수)

## 📦 설치 방법

### 1. 저장소 클론
```bash
git clone <repository-url>
cd rtsp_simulator
```

### 2. 프로젝트 구조 확인
```
rtsp_simulator/
├── rtsp_simulator_ffmpeg_v2.py  # 메인 프로그램
├── media/                       # 입력 비디오 파일 폴더
│   ├── README.md               # 사용법 안내
│   └── .gitkeep               # Git 추적용
├── output/                     # 출력 비디오 파일 폴더  
│   ├── README.md              # 출력 구조 안내
│   └── .gitkeep              # Git 추적용
├── .env.example               # 환경변수 템플릿
├── README.md                  # 프로젝트 문서
├── requirements.txt           # Python 패키지 종속성
├── .gitignore                # Git 무시 파일
└── .gitmessage.txt          # 커밋 메시지 템플릿
```

### 3. 환경변수 설정
```bash
# .env.example 파일을 .env로 복사
cp .env.example .env

# .env 파일을 환경에 맞게 수정
nano .env  # 또는 선호하는 에디터 사용
```

주요 환경변수:
- `BLUR_MODULE_PATH`: 블러 모듈 경로 (기본: ./blur_module/ipcamera_blur.py)
- `DEFAULT_MEDIA_PATH`: 입력 미디어 폴더 (기본: ./media)
- `DEFAULT_OUTPUT_PATH`: 출력 폴더 (기본: ./output)
- `DEFAULT_THREAD_COUNT`: 기본 스레드 수 (기본: 6)
- `DEFAULT_INPUT_FPS`: 기본 입력 FPS (기본: 15.0)

### 4. Python 패키지 설치
```bash
# 필수 패키지 설치
pip install -r requirements.txt

# 또는 개별 설치
pip install opencv-python
pip install pillow
pip install numpy
pip install psutil
pip install python-dotenv
pip install GPUtil  # GPU 모니터링용 (선택사항)
```

### 5. FFmpeg 설치
#### Windows
1. [FFmpeg 다운로드](https://ffmpeg.org/download.html)
2. 압축 해제 후 환경변수 PATH에 추가

#### macOS
```bash
brew install ffmpeg
```

#### Ubuntu/Debian
```bash
sudo apt update
sudo apt install ffmpeg
```

### 5. 실행
```bash
python rtsp_simulator_ffmpeg_v2.py
```

## 🚀 사용 방법

### 기본 실행
1. 프로그램 실행 후 GUI 인터페이스 확인
2. **미디어 파일 준비**: `media/` 폴더에 처리할 비디오 파일 복사
3. **소스 설정**에서 "파일 선택" 버튼으로 파일 선택 또는 RTSP URL 입력
4. **저장 설정**에서 출력 경로 확인 (기본: `./output/`)
5. **시작** 버튼 클릭으로 처리 시작

### 소스 설정 예시
```
RTSP 스트림: rtsp://username:password@192.168.1.100:554/stream1
HTTP 스트림: http://192.168.1.100:8080/video
로컬 파일: ./media/sample.mp4
다중 파일: ./media/video1.mp4, ./media/video2.mp4, ...
```

### 고급 설정

#### 🎨 블러 모듈 설정
사용자 정의 블러 처리 모듈을 연결할 수 있습니다:
```python
# blur_module.py 예시
class HeadBlurrer:
    def __init__(self, model_path, num_camera):
        # YOLO 모델 초기화
        pass
    
    def process_frame(self, frame, camera_index):
        # 얼굴 탐지 및 블러 처리
        return processed_frame

# 또는 함수 형태
def apply_blur(frame, thread_id):
    # 커스텀 블러 처리
    return processed_frame
```

#### 🎬 코덱 최적화 가이드
| 용도 | 권장 코덱 | 설정 |
|------|-----------|------|
| 실시간 스트리밍 | H.264 (libx264) | preset=fast, crf=23 |
| 고품질 저장 | H.265 (libx265) | preset=medium, crf=20 |
| 웹 호환성 | VP9 | 품질모드=CBR, 2M bitrate |
| 최소 용량 | AV1 | preset=slow, crf=30 |

#### ⚙️ 성능 튜닝
```
- 스레드 수: CPU 코어 수의 50-75%
- 처리 큐 크기: 메모리에 따라 조정 (기본: 1000)
- FPS: 소스 FPS와 일치 (기본: 15)
- 압축 레벨: 0(빠름/큰파일) ~ 9(느림/작은파일)
```

## 📊 모니터링 및 통계

### 실시간 통계
- **프레임 통계**: 수신/처리/저장/손실 프레임 수
- **성능 지표**: 처리 속도, 손실률, 저장률
- **리소스 사용량**: CPU, RAM, GPU 사용률
- **성능 프로파일**: 각 처리 단계별 소요 시간

### 성능 보고서
프로그램에서 자동으로 생성되는 JSON 형태의 상세 보고서:
- 프레임 처리 통계
- 코덱 성능 정보
- 리소스 사용 히스토리
- 성능 프로파일링 데이터

## 🔧 설정 옵션

### 기본 설정
- **스레드 수**: 1-10개 (기본: 6)
- **최대 프레임**: 제한 없음 또는 특정 수
- **프레임 손실률**: 시뮬레이션용 (0-100%)
- **재연결 간격**: RTSP 연결 실패 시 (기본: 5초)

### 저장 설정
- **저장 활성화**: 영상 파일 저장 여부
- **저장 경로**: 출력 폴더 지정
- **저장 간격**: 영상 파일 분할 간격 (초)
- **파일 형식**: MP4, MKV, WebM, AVI

### 오버레이 설정
- **GPS 좌표**: 위도/경도 표시
- **프레임 정보**: 프레임 번호, 시간, 스레드 ID
- **위치**: 영상 좌상단에 자동 표시

## 🎯 사용 사례

### 1. 보안 카메라 모니터링
```
- 다중 RTSP 카메라 동시 모니터링
- 실시간 얼굴 블러링으로 프라이버시 보호
- 고효율 압축으로 저장공간 절약
```

### 2. 스트리밍 서비스
```
- 실시간 영상 처리 및 재전송
- 다양한 코덱으로 호환성 확보
- 하드웨어 가속으로 성능 최적화
```

### 3. 비디오 분석 시스템
```
- AI 모델 통합으로 객체 탐지
- 대용량 비디오 배치 처리
- 상세한 성능 모니터링
```

## 🚨 문제 해결

### 일반적인 문제

#### FFmpeg 관련
```
문제: "FFmpeg가 설치되지 않았습니다" 오류
해결: FFmpeg 설치 및 PATH 환경변수 확인
```

#### RTSP 연결 실패
```
문제: RTSP 스트림 연결 불가
해결: 
1. URL 형식 확인 (rtsp://user:pass@ip:port/path)
2. 네트워크 연결 상태 확인
3. 카메라 인증 정보 확인
```

#### 성능 이슈
```
문제: 실시간 처리 속도 부족
해결:
1. 스레드 수 조정
2. 하드웨어 가속 활성화
3. 코덱 프리셋을 'fast' 또는 'ultrafast'로 변경
4. 압축 레벨 낮추기
```

#### GPU 인식 불가
```
문제: GPU 모니터링 불가
해결:
1. GPUtil 패키지 설치: pip install GPUtil
2. GPU 드라이버 업데이트
3. CUDA 설치 (NVIDIA GPU)
```

### 로그 확인
프로그램 실행 시 콘솔에서 상세한 로그 확인:
```
[12:34:56] INFO - 소스 프로세서 시작됨 - 쓰레드 수: 6
[12:34:57] INFO - 쓰레드 0: RTSP 연결 시도 - rtsp://192.168.1.100:554/stream1
[12:34:58] INFO - 쓰레드 0: 소스 연결 성공
```

## 📄 라이센스

이 프로젝트는 MIT 라이센스 하에 배포됩니다.

## 🤝 기여하기

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📞 지원

문의사항이나 버그 리포트는 Issue를 통해 제출해주세요.

---

**개발자**: RTSP Simulator Team  
**버전**: v2.0  
**최종 업데이트**: 2025년 1월
