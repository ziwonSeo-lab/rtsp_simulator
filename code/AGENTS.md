<!-- Parent: ../AGENTS.md -->
# code - RTSP 시뮬레이터 소스 코드

## Purpose

RTSP 스트림 처리 시뮬레이터의 핵심 소스 코드 디렉토리입니다. 멀티프로세스 기반 RTSP 송수신, 클라이언트 모듈, 녹화 처리 등을 포함합니다.

## Subdirectories

### 핵심 모듈

- `multi_rtspsender/` - 멀티 RTSP 송신 모듈 [→ multi_rtspsender/AGENTS.md]
  - MediaMTX 기반 RTMP → RTSP 변환
  - 최대 6개 스트림 동시 송신
  - 경로: `src/server/rtsp_sender.py`

- `rtsp_client_module/` - RTSP 클라이언트 모듈 [→ rtsp_client_module/AGENTS.md]
  - 멀티프로세스 기반 수신/처리
  - FFmpeg 기반 비디오 인코딩
  - GUI/헤드리스 모드 지원

- `rtsp_save_process/` - 녹화 및 저장 처리
  - 비디오 파일 저장
  - 처리 큐 관리

### 보조 모듈

- `rtsp_gui/` - GUI 관련 코드
- `media_process/` - 미디어 처리 유틸리티
- `muilty_rtspsender_gui/` - 멀티 RTSP 송신 GUI

## For AI Agents

### 데이터 흐름

```
비디오 파일
  ↓ (FFmpeg concat)
RTMP → localhost:1911-1916
  ↓ (MediaMTX 변환)
RTSP → 10.2.10.158:1111-1116
  ↓ (rtsp_client_module 수신)
프레임 처리 (블러 등)
  ↓
비디오 저장 / 미리보기
```

### 주요 실행 명령

```bash
# MediaMTX 시작
cd multi_rtspsender/scripts/management
bash start_all_mediamtx.sh

# RTSP 송신 시작
cd multi_rtspsender
nohup sudo python3 src/server/rtsp_sender.py -c config/config_noloss.json 2>&1 &

# 클라이언트 실행 (GUI)
cd rtsp_client_module
python run_with_gui.py

# 클라이언트 실행 (헤드리스)
python run_headless.py --save --duration 60
```

### 모듈 간 연동

1. `multi_rtspsender`: RTSP 스트림 생성
2. `rtsp_client_module`: 스트림 수신 및 처리
3. `blur_module` (상위): AI 블러 처리
4. `rtsp_save_process`: 결과 저장

## Dependencies

- FFmpeg
- MediaMTX
- OpenCV
- psutil, GPUtil
