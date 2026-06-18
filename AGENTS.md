<!-- Parent: ../AGENTS.md -->
# rtsp_simulator - RTSP 스트림 처리 시뮬레이터 v2

## Purpose

고성능 RTSP 스트림 및 비디오 파일 처리 시뮬레이터입니다. 최대 10개의 동시 스트림을 처리하며, CUDA 12.1 + TensorRT 10.0 기반 실시간 AI 영상 처리와 다양한 비디오 코덱 인코딩을 지원합니다.

## Key Files

### 메인 프로그램
- `rtsp_simulator_ffmpeg_v2.py` - 메인 GUI 프로그램 (코드 디렉토리에 있을 수 있음)
- `install_ai_packages.sh` - 원클릭 AI 패키지 설치 스크립트
- `requirements.txt` - Python 의존성
- `monitor_system.sh` - 시스템 모니터링 스크립트

### 테스트 스크립트
- `test_stream_independent_fps.py` - 독립 FPS 제어 테스트
- `test_disk_io_performance.py` - 디스크 I/O 성능 테스트
- `test_env_model_path.py` - 환경변수 및 모델 경로 테스트
- `test_fps_fix.py` - FPS 수정 테스트
- `debug_fps_monitoring.py` - FPS 모니터링 디버그

### 설정
- `.env`, `.env.example` - 환경 변수
- `.coderabbit.yaml` - CodeRabbit 설정
- `.projectrules` - 프로젝트 규칙
- `PRD.md` - 제품 요구사항 문서

### 로그
- `debug_fps_monitoring.log` - FPS 모니터링 로그
- `test_shared_fps_control.log` - 공유 FPS 제어 테스트 로그
- `disk_io_test.log` - 디스크 I/O 테스트 로그

## Subdirectories

- `code/` - 핵심 소스 코드 [→ code/AGENTS.md]
  - `multi_rtspsender/` - 멀티 RTSP 송신 모듈
  - `rtsp_client_module/` - RTSP 클라이언트 모듈
  - `rtsp_save_process/` - 녹화 및 저장 처리
  - `rtsp_gui/` - GUI 관련
  - `media_process/` - 미디어 처리
- `blur_module/` - AI 블러 모듈 (HeadBlurrer) [→ blur_module/AGENTS.md]
- `media/` - 입력 비디오 파일
- `output/` - 출력 비디오 파일
- `env-blur/` - Python 가상환경
- `debug_fps_output/` - FPS 디버그 출력
- `test_output/` - 테스트 출력

## For AI Agents

### 핵심 기능

1. **멀티스레드 처리**: 최대 10개 독립 스레드
2. **GPU 가속**: CUDA 12.1 + TensorRT 10.0
3. **다양한 코덱**: H.264, H.265, VP9, AV1
4. **실시간 모니터링**: CPU/GPU 온도, 사용률

### 성능 벤치마크 (RTX 4070 SUPER)

| 코덱 | 설정 | 성능 |
|------|------|------|
| H.264 + TensorRT | preset=fast | ~240 FPS |
| H.265 + TensorRT | preset=medium | ~120 FPS |
| H.264 CPU only | - | ~30 FPS |

### 환경 설정

```bash
# 가상환경 활성화
source env-blur/bin/activate

# AI 패키지 설치
./install_ai_packages.sh

# 프로그램 실행
python rtsp_simulator_ffmpeg_v2.py
```

### 블러 모듈 통합

```python
from blur_module.ipcamera_blur import HeadBlurrer

blurrer = HeadBlurrer(model_path, num_camera)
processed_frame = blurrer.process_frame(frame, camera_index)
```

### 작업 시 주의사항

- FFmpeg 시스템 설치 필요
- NVIDIA GPU 드라이버 최신 버전 권장
- 멀티 스트림 처리 시 메모리 사용량 주의

## Dependencies

- Python 3.7+ (3.9+ 권장)
- PyTorch 2.5.1 + CUDA 12.1
- TensorRT 10.0
- FFmpeg
- OpenCV, Ultralytics YOLO
- GPUtil, psutil

## Commands

```bash
# 환경 활성화
source env-blur/bin/activate

# 시스템 요구사항 확인
python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}')"
ffmpeg -version

# GPU 상태 모니터링
watch -n 1 nvidia-smi

# 디스크 I/O 테스트
python test_disk_io_performance.py
```
