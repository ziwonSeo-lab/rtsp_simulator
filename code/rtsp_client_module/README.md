# RTSP 클라이언트 모듈

`multi-process_rtsp.py`에서 추출된 모듈화된 RTSP 클라이언트 시스템입니다.

## 모듈 구조

```
rtsp_client_module/
├── __init__.py           # 모듈 초기화 및 공개 API
├── config.py            # RTSP 설정 및 환경변수 관리
├── statistics.py        # 프레임 통계 및 시스템 리소스 모니터링
├── video_writer.py      # FFmpeg 기반 비디오 라이터
├── workers.py           # 멀티프로세스 워커 함수들
├── processor.py         # RTSP 처리 메인 프로세서
├── gui.py              # 기본 GUI 인터페이스
├── example.py          # 사용 예제
└── README.md           # 이 문서
```

## 주요 컴포넌트

### 1. RTSPConfig (config.py)
RTSP 처리에 필요한 모든 설정을 관리합니다.

```python
from rtsp_client_module import RTSPConfig

config = RTSPConfig(
    sources=["rtsp://example.com/stream"],
    thread_count=2,
    blur_workers=1,
    save_workers=1,
    save_enabled=True,
    save_path="./output/"
)
```

### 2. SharedPoolRTSPProcessor (processor.py)
메인 RTSP 처리 시스템으로 멀티프로세스를 관리합니다.

```python
from rtsp_client_module import SharedPoolRTSPProcessor

processor = SharedPoolRTSPProcessor(config)
processor.start()
# ... 처리 ...
processor.stop()
```

### 3. 통계 모듈 (statistics.py)
- `FrameStatistics`: 프레임 처리 통계
- `FrameCounter`: 프레임 카운터 및 FPS 계산
- `ResourceMonitor`: 시스템 리소스 모니터링
- `PerformanceProfiler`: 성능 프로파일링

### 4. 워커 프로세스 (workers.py)
- `rtsp_capture_process`: RTSP 스트림 캡처
- `blur_worker_process`: 블러 처리
- `save_worker_process`: 비디오 파일 저장

### 5. 비디오 라이터 (video_writer.py)
FFmpeg 기반의 고성능 비디오 인코더입니다.

### 6. GUI (gui.py)
기본적인 GUI 인터페이스를 제공합니다.

```python
from rtsp_client_module import create_gui

root, app = create_gui()
root.mainloop()
```

## 사용법

### 기본 사용법

```python
import logging
from rtsp_client_module import RTSPConfig, SharedPoolRTSPProcessor

# 로깅 설정
logging.basicConfig(level=logging.INFO)

# 설정 생성
config = RTSPConfig(
    sources=["rtsp://example.com/stream"],
    thread_count=1,
    save_enabled=True
)

# 프로세서 실행
processor = SharedPoolRTSPProcessor(config)
processor.start()

# 처리 중...
import time
time.sleep(30)

# 종료
processor.stop()
```

### GUI 사용법

```python
from rtsp_client_module import create_gui

root, app = create_gui()
root.mainloop()
```

## 예제 실행

```bash
cd rtsp_client_module
python example.py
```

## 의존성

- cv2 (OpenCV)
- numpy  
- psutil
- PIL (Pillow)
- tkinter
- GPUtil (선택사항)

## 특징

- 멀티프로세스 기반 고성능 처리
- FFmpeg 기반 고품질 비디오 인코딩
- 실시간 시스템 리소스 모니터링
- 프레임 손실 시뮬레이션
- 블러 처리 및 오버레이 지원
- 모듈화된 구조로 재사용 가능


● 🚀 실행 방법

  1. GUI 포함 실행

  cd /home/szw001/development/2025/IUU/rtsp_simulator/code/rtsp_client_module
  python run_with_gui.py

  2. GUI 없이 실행 (헤드리스)

  cd /home/szw001/development/2025/IUU/rtsp_simulator/code/rtsp_client_module

  # 기본 실행
  python run_headless.py

  # 옵션과 함께 실행
  python run_headless.py --sources rtsp://stream1 rtsp://stream2 --threads 4 --duration
  60 --save --save-path ./videos/

  # 도움말 보기
  python run_headless.py --help

  📋 헤드리스 모드 옵션들

  - --sources: RTSP 소스 URL들 (여러 개 가능)
  - --threads: 스레드 수 (기본값: 2)
  - --duration: 실행 시간(초) - 0이면 무한 실행
  - --save: 비디오 저장 활성화
  - --save-path: 저장 경로
  - --fps: 입력 FPS
  - --log-level: 로그 레벨 (DEBUG/INFO/WARNING/ERROR)
  - --frame-loss-rate: 프레임 손실률 시뮬레이션

  🎯 사용 예시

  # GUI로 실행
  python run_with_gui.py

  # 헤드리스로 30초간 실행
  python run_headless.py --duration 30

  # 비디오 저장하며 무한 실행
  python run_headless.py --save --save-path ./output/

  이제 상황에 맞게 GUI나 헤드리스 모드를 선택해서 사용할 수 있습니다!


  # 실제 실행 명령어 

  python run_headless.py --save

  # 실시간 통계 모니터링링
  code/rtsp_client_module/show_stats.py