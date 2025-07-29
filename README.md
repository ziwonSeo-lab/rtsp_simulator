git # RTSP 시뮬레이터 v2 🎥

고성능 RTSP 스트림 및 비디오 파일 처리 시뮬레이터입니다. 스레드별 독립적인 YOLO/HeadBlurrer 인스턴스를 지원하며, 실시간 영상 처리와 다양한 비디오 코덱을 통한 고품질 영상 저장이 가능합니다.

## 📋 주요 기능

### 🎯 핵심 특징
- **🆕 모듈화된 구조**: 재사용 가능한 RTSP 클라이언트 모듈
- **듀얼 실행 모드**: GUI와 헤드리스 모드 모두 지원
- **멀티프로세스 처리**: 독립된 프로세스로 안정적인 병렬 처리 (18개 프로세스)
- **스레드별 AI 모델**: 각 스레드마다 독립적인 YOLO/HeadBlurrer 인스턴스로 GPU 경합 해결
- **실시간 영상 처리**: 얼굴 블러링, 객체 탐지 등 커스텀 모듈 지원
- **고급 비디오 인코딩**: FFmpeg 기반 다양한 코덱 및 압축 옵션
- **실시간 모니터링**: CPU, RAM, GPU 사용률 및 성능 프로파일링
- **직관적 GUI**: 스크롤 가능한 설정 패널과 실시간 미리보기
- **프레임/패킷 손실 추적**: 상세한 통계 및 오류 분석

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
├── code/
│   ├── rtsp_gui/                      # 기존 GUI 프로그램들
│   │   ├── rtsp_simulator_ffmpeg_v2.py  # 원본 메인 프로그램
│   │   └── multi-process_rtsp.py      # 멀티프로세스 버전
│   └── rtsp_client_module/            # 🆕 모듈화된 RTSP 클라이언트
│       ├── __init__.py               # 모듈 초기화
│       ├── config.py                 # 설정 관리
│       ├── statistics.py             # 통계 및 모니터링
│       ├── video_writer.py           # FFmpeg 비디오 라이터
│       ├── workers.py                # 멀티프로세스 워커들
│       ├── processor.py              # 메인 프로세서
│       ├── gui.py                    # GUI 템플릿
│       ├── run_with_gui.py          # 🚀 GUI 실행파일
│       ├── run_headless.py          # 🚀 헤드리스 실행파일
│       └── README.md                # 모듈 사용법
├── blur_module/                       # 블러 처리 모듈
│   ├── ipcamera_blur.py              # HeadBlurrer 클래스
│   └── models/                       # YOLO 모델 파일들
├── media/                            # 입력 비디오 파일 폴더
│   ├── README.md                    # 사용법 안내
│   └── .gitkeep                    # Git 추적용
├── output/                           # 출력 비디오 파일 폴더  
│   ├── README.md                   # 출력 구조 안내
│   └── .gitkeep                   # Git 추적용
├── .env.example                     # 환경변수 템플릿
├── README.md                        # 이 문서
├── requirements.txt                 # Python 패키지 종속성
├── .gitignore                      # Git 무시 파일
└── .gitmessage.txt                # 커밋 메시지 템플릿
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

## 🚀 사용 방법

### 🆕 모듈화된 RTSP 클라이언트 (권장)

#### GUI 모드 실행
```bash
cd code/rtsp_client_module
python run_with_gui.py
```

#### 헤드리스 모드 실행
```bash
cd code/rtsp_client_module

# 기본 실행 (config.py의 설정 사용)
python run_headless.py --save

# 사용자 정의 실행
python run_headless.py --sources rtsp://stream1 rtsp://stream2 --threads 4 --duration 60 --save --save-path ./videos/

# 도움말 확인
python run_headless.py --help
```

#### 헤드리스 모드 주요 옵션
- `--sources`: RTSP 소스 URL들 (여러 개 가능, 기본값: config.py 설정)
- `--threads`: 스레드 수 (기본값: config.py에서 6개)
- `--duration`: 실행 시간(초) - 0이면 무한 실행
- `--save`: 비디오 저장 활성화
- `--save-path`: 저장 경로 (기본값: ./output/)
- `--fps`: 입력 FPS (기본값: 15.0)
- `--log-level`: 로그 레벨 (DEBUG/INFO/WARNING/ERROR)
- `--frame-loss-rate`: 프레임 손실률 시뮬레이션

### 기존 GUI 프로그램 (레거시)
```bash
cd code/rtsp_gui
python rtsp_simulator_ffmpeg_v2.py  # 원본 GUI 프로그램
python multi-process_rtsp.py        # 멀티프로세스 버전
```

### 기본 사용법
1. **config.py 설정 확인**: `code/rtsp_client_module/config.py`에서 기본 RTSP 소스들과 설정 확인
2. **GUI 모드**: 직관적인 인터페이스로 설정 변경 가능
3. **헤드리스 모드**: 서버 환경이나 자동화에 적합
4. **출력 확인**: `./output/` 폴더에서 처리된 비디오 파일 확인

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
- 다중 RTSP 카메라 동시 모니터링 (최대 6개 소스)
- 실시간 얼굴 블러링으로 프라이버시 보호
- 고효율 압축으로 저장공간 절약
- 프레임 손실 및 오류 통계 추적
```

### 2. 서버 환경 자동화
```
- 헤드리스 모드로 GUI 없이 실행
- 명령행 인자로 유연한 설정 제어
- 로그 파일 기반 모니터링
- 시간 제한 및 자동 종료 기능
```

### 3. 개발 및 테스트 환경
```
- 모듈화된 구조로 쉬운 커스터마이징
- config.py 기반 중앙화된 설정 관리
- 블러 모듈 동적 로딩
- 상세한 성능 프로파일링
```

### 4. 비디오 분석 시스템
```
- AI 모델 통합으로 객체 탐지
- 멀티프로세스 기반 고성능 처리
- FFmpeg 기반 고품질 인코딩
- 실시간 통계 및 모니터링
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

## 📚 추가 문서

- [RTSP 클라이언트 모듈 사용법](code/rtsp_client_module/README.md)
- [블러 모듈 설정 가이드](blur_module/README.md)
- [환경변수 설정 예시](.env.example)

---

**개발자**: RTSP Simulator Team  
**버전**: v2.1 - 모듈화 버전  
**최종 업데이트**: 2025년 1월

### 🔄 버전 히스토리
- **v2.1**: RTSP 클라이언트 모듈화, GUI/헤드리스 듀얼 모드, 멀티프로세스 개선
- **v2.0**: FFmpeg 통합, 멀티스레드 처리, GUI 개선
- **v1.x**: 초기 RTSP 스트림 처리 구현
