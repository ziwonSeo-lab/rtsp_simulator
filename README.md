# RTSP 시뮬레이터 v2 🎥

고성능 RTSP 스트림 및 비디오 파일 처리 시뮬레이터입니다. 스레드별 독립적인 YOLO/HeadBlurrer 인스턴스를 지원하며, **CUDA 12.1 + TensorRT 10.0** 기반 실시간 영상 처리와 다양한 비디오 코덱을 통한 고품질 영상 저장이 가능합니다.

## 🆕 v2 주요 업데이트

### 🚀 GPU 가속 및 모니터링
- **CUDA 12.1 + TensorRT 10.0** 완전 지원
- **GPU 온도 실시간 모니터링** (CPU 온도도 지원)
- **원클릭 AI 패키지 설치** 스크립트 (`install_ai_packages.sh`)
- **PyTorch 2.5.1 + CUDA 12.1** 호환성

### 📊 향상된 모니터링
- **리소스 사용량**: CPU/RAM/GPU 사용률 및 온도
- **성능 프로파일링**: 처리 단계별 소요 시간 분석
- **통합 성능 보고서**: JSON 형태의 상세 분석 보고서

## 📋 주요 기능

### 🎯 핵심 특징
- **멀티스레드 처리**: 최대 10개의 독립적인 스레드로 여러 RTSP 소스 동시 처리
- **스레드별 AI 모델**: 각 스레드마다 독립적인 YOLO/HeadBlurrer 인스턴스로 GPU 경합 해결
- **실시간 영상 처리**: 얼굴 블러링, 객체 탐지 등 커스텀 모듈 지원
- **고급 비디오 인코딩**: FFmpeg 기반 다양한 코덱 및 압축 옵션
- **실시간 모니터링**: CPU/GPU 온도, 사용률, 성능 프로파일링
- **직관적 GUI**: 스크롤 가능한 설정 패널과 실시간 미리보기

### 🎬 지원 비디오 코덱
- **H.264 (libx264)**: 범용 호환성, 실시간 스트리밍
- **H.265 (libx265)**: 고효율 압축, 저장 공간 절약
- **VP9 (libvpx-vp9)**: 웹 최적화, YouTube 호환
- **AV1 (libaom-av1)**: 차세대 압축, 최고 효율
- **XVID, H.262**: 레거시 시스템 지원

### 📁 지원 컨테이너 포맷
- **MP4**: 범용 호환성 (권장)
- **MKV**: 고급 기능 지원
- **WebM**: 웹 스트리밍
- **AVI**: 레거시 호환성

### ⚡ 하드웨어 가속 지원
- **NVIDIA CUDA 12.1**: h264_nvenc, hevc_nvenc + TensorRT 10.0
- **Intel Quick Sync**: QSV 가속
- **AMD AMF**: AMD 하드웨어 가속

### 🌡️ 실시간 리소스 모니터링
- **CPU**: 사용률, 온도, 코어 정보
- **RAM**: 시스템 전체 및 프로세스별 사용량
- **GPU**: 사용률, 메모리, 온도 (NVIDIA GPU)
- **성능**: 프레임 처리 속도, 처리 단계별 소요 시간

## 🛠️ 시스템 요구사항

### 필수 요구사항
- **Python**: 3.7 이상 (3.9+ 권장)
- **운영체제**: Windows 10/11, macOS 10.15+, Ubuntu 20.04+
- **RAM**: 최소 8GB (16GB 권장)
- **CPU**: 멀티코어 프로세서 (8코어+ 권장)
- **저장공간**: 10GB 이상 (AI 모델 및 영상 저장용)

### GPU 가속 요구사항 (권장)
- **NVIDIA GPU**: RTX 20xx 이상 (RTX 40xx 권장)
- **VRAM**: 최소 6GB (12GB+ 권장)
- **CUDA**: 12.1 호환 드라이버
- **Compute Capability**: 7.5 이상

### 추가 요구사항
- **FFmpeg**: 고급 비디오 인코딩용 (필수)
- **cmake**: AI 패키지 빌드용
- **인터넷 연결**: AI 모델 다운로드용

## 📦 설치 방법

### 🚀 방법 1: 원클릭 설치 (권장)

```bash
# 1. 저장소 클론
git clone <repository-url>
cd rtsp_simulator

# 2. 가상환경 생성 및 활성화
python -m venv env-blur
source env-blur/bin/activate  # Linux/macOS
# env-blur\Scripts\activate     # Windows

# 3. 원클릭 AI 패키지 설치
./install_ai_packages.sh
```

### 🛠️ 방법 2: 수동 설치

```bash
# 1. 기본 패키지 설치
pip install -r requirements.txt

# 2. PyTorch CUDA 12.1 설치
pip install torch==2.5.1+cu121 torchvision==0.20.1+cu121 \
            --index-url https://download.pytorch.org/whl/cu121

# 3. 시스템 의존성 (Ubuntu/Debian)
sudo apt-get install -y cmake ffmpeg

# 4. TensorRT 설치 (NVIDIA GPU)
pip install tensorrt-cu12==10.0.1 \
            tensorrt-cu12-bindings==10.0.1 \
            tensorrt-cu12-libs==10.0.1 \
            --extra-index-url https://pypi.ngc.nvidia.com

# 5. YOLO 업그레이드
pip install --upgrade ultralytics
```

### 🔍 설치 확인

```bash
# GPU 확인
python -c "import GPUtil; print(f'GPU: {len(GPUtil.getGPUs())}개 감지')"

# CUDA 확인
python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}')"

# TensorRT 확인 (선택사항)
python -c "import tensorrt; print(f'TensorRT: {tensorrt.__version__}')"
```

## 🚀 사용 방법

### 1. 프로그램 실행
```bash
# 가상환경 활성화
source env-blur/bin/activate

# 프로그램 실행
python rtsp_simulator_ffmpeg_v2.py
```

### 2. 기본 설정

#### 📹 소스 설정
- **RTSP URL**: `rtsp://username:password@ip:port/path`
- **로컬 파일**: `./media/sample.mp4`
- **다중 소스**: 최대 8개 동시 처리

#### 🎨 AI 블러 모듈 (선택사항)
```python
# blur_module/ipcamera_blur.py 예시
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
| 용도 | 권장 코덱 | 설정 | 예상 성능 |
|------|-----------|------|-----------|
| 실시간 스트리밍 | H.264 + CUDA | preset=fast, CRF=23 | ~240 FPS |
| 고품질 저장 | H.265 + TensorRT | preset=medium, CRF=20 | ~120 FPS |
| 웹 호환성 | VP9 | CBR, 2M bitrate | ~150 FPS |
| 최소 용량 | AV1 | preset=slow, CRF=30 | ~60 FPS |

### 3. 성능 튜닝

#### ⚙️ 권장 설정
```
- 스레드 수: CPU 코어 수의 50-75%
- 처리 큐 크기: 메모리에 따라 조정 (기본: 1000)
- FPS: 소스 FPS와 일치 (기본: 15)
- 압축 레벨: 6 (균형) | 0 (빠름) | 9 (고압축)
```

#### 📊 성능 벤치마크 (RTX 4070 SUPER 기준)
- **H.264 + TensorRT**: ~240 FPS
- **H.265 + TensorRT**: ~120 FPS  
- **H.264 CPU 전용**: ~30 FPS
- **H.265 CPU 전용**: ~15 FPS

## 📊 모니터링 및 통계

### 🌡️ 실시간 리소스 모니터링
```
💻 리소스 모니터링
CPU 사용률:    45.2% / 100% (🖥️16코어)
CPU 온도:      65.3°C
RAM 사용률:    67.8% (10.8/16.0GB)
GPU 사용률:    75.3% / 100%
GPU 온도:      55.8°C
GPU 메모리:    77.5% (9.3/12.0GB)
```

### ⏱️ 성능 프로파일링
- **프레임 처리**: 각 단계별 소요 시간
- **블러 처리**: AI 모델 실행 시간
- **인코딩**: 비디오 압축 성능
- **저장**: 파일 I/O 성능

### 📈 통합 성능 보고서
프로그램에서 자동 생성되는 JSON 형태의 상세 보고서:
- 프레임 처리 통계
- 코덱 성능 정보  
- 리소스 사용 히스토리
- CPU/GPU 온도 기록
- 성능 프로파일링 데이터

## 🔧 설정 옵션

### 기본 설정
- **스레드 수**: 1-10개 (기본: 6)
- **최대 프레임**: 제한 없음 또는 특정 수
- **프레임 손실률**: 시뮬레이션용 (0-100%)
- **재연결 간격**: RTSP 연결 실패 시 (기본: 5초)

### 저장 설정  
- **저장 활성화**: 영상 파일 저장 여부
- **저장 경로**: 출력 폴더 지정 (기본: `./output/`)
- **저장 간격**: 영상 파일 분할 간격 (초)
- **파일 형식**: MP4, MKV, WebM, AVI

### 오버레이 설정
- **GPS 좌표**: 위도/경도 표시 (서울 기본값)
- **프레임 정보**: 프레임 번호, 시간, 스레드 ID
- **위치**: 영상 좌상단에 자동 표시

## 🎯 사용 사례

### 1. 보안 카메라 모니터링
```
- 다중 RTSP 카메라 동시 모니터링 (최대 10개)
- 실시간 얼굴 블러링으로 프라이버시 보호
- GPU 가속으로 240+ FPS 실시간 처리
- 고효율 압축으로 저장공간 80% 절약
```

### 2. 스트리밍 서비스
```
- 실시간 영상 처리 및 재전송
- 다양한 코덱으로 호환성 확보
- TensorRT 최적화로 지연시간 최소화
- 하드웨어 가속으로 전력 효율성 향상
```

### 3. 비디오 분석 시스템
```
- AI 모델 통합으로 객체/얼굴 탐지
- 대용량 비디오 배치 처리
- 상세한 성능 모니터링 및 최적화
- 처리 결과 자동 보고서 생성
```

## 🚨 문제 해결

### 일반적인 문제

#### 🔧 GPU 관련
```
문제: GPU 사용량/온도가 표시되지 않음
해결: 
1. pip install GPUtil
2. NVIDIA 드라이버 최신 버전 설치
3. 가상환경에 GPUtil 재설치
```

#### 🎬 FFmpeg 관련
```
문제: "FFmpeg가 설치되지 않았습니다" 오류
해결: 
- Ubuntu: sudo apt install ffmpeg
- Windows: https://ffmpeg.org/download.html 에서 다운로드
- macOS: brew install ffmpeg
```

#### 🚀 CUDA/TensorRT 관련
```
문제: CUDA 인식 불가
해결:
1. nvidia-smi 명령어로 GPU 확인
2. CUDA 12.1 호환 드라이버 설치
3. ./install_ai_packages.sh 재실행
```

#### 📡 RTSP 연결 실패
```
문제: RTSP 스트림 연결 불가
해결: 
1. URL 형식 확인: rtsp://user:pass@ip:port/path
2. 네트워크 연결 상태 확인
3. 카메라 인증 정보 확인
4. 방화벽/포트 설정 확인
```

#### ⚡ 성능 이슈
```
문제: 실시간 처리 속도 부족
해결:
1. GPU 사용률 확인 (70% 이하인 경우)
2. 스레드 수 조정 (CPU 코어 수의 75%)
3. 코덱 프리셋을 'fast' 또는 'ultrafast'로 변경
4. 압축 레벨 낮추기 (6→3 또는 0)
5. TensorRT 최적화 활성화
```

### 🔍 디버깅 도구

#### 로그 확인
```bash
# 프로그램 실행 시 상세 로그
python rtsp_simulator_ffmpeg_v2.py --log-level DEBUG

# GPU 상태 실시간 모니터링
watch -n 1 nvidia-smi
```

#### 성능 분석
- GUI 내 **성능 프로파일** 탭 확인
- **📊 성능 보고서 저장** 버튼으로 상세 분석
- **리소스 모니터링** 패널에서 실시간 상태 확인

## 📁 프로젝트 구조
```
rtsp_simulator/
├── rtsp_simulator_ffmpeg_v2.py    # 메인 프로그램
├── install_ai_packages.sh         # AI 패키지 설치 스크립트
├── requirements.txt               # Python 패키지 종속성
├── README.md                      # 프로젝트 문서
├── blur_module/                   # 사용자 AI 모듈 (선택사항)
│   ├── ipcamera_blur.py          # 블러 모듈 예시
│   └── models/                    # AI 모델 파일들
├── media/                         # 입력 비디오 파일 폴더
├── output/                        # 출력 비디오 파일 폴더
└── env-blur/                      # Python 가상환경
```

## 🚀 다음 업데이트 계획

### v2.1 (예정)
- [ ] **멀티 GPU 지원**: 여러 GPU 동시 사용
- [ ] **클라우드 스트리밍**: AWS/Azure 연동
- [ ] **웹 인터페이스**: 브라우저 기반 제어
- [ ] **Docker 지원**: 컨테이너 배포

### v2.2 (예정)  
- [ ] **RTMP 스트리밍**: 실시간 방송 지원
- [ ] **객체 추적**: 다중 객체 트래킹
- [ ] **모션 감지**: 이벤트 기반 녹화
- [ ] **클러스터링**: 분산 처리 지원

## �� 라이센스

이 프로젝트는 MIT 라이센스 하에 배포됩니다.

## 🤝 기여하기

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📞 지원 및 문의

- **이슈 리포트**: GitHub Issues
- **기능 요청**: GitHub Discussions
- **문서 개선**: Pull Request 환영

---

**🎉 RTSP 시뮬레이터 v2로 고성능 영상 처리를 경험해보세요!**
