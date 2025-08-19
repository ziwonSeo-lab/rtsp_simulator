# RTSP Multithread Processor (멀티 스트림 운영 가이드)

이 디렉터리는 RTSP 스트림을 멀티 프로세스로 병렬 처리하여 YOLO 블러, 오버레이, MP4 저장, 자막(SRT) 작성, 최종 경로 자동 이동까지 수행하는 운영 스크립트/모듈을 포함합니다. 이 README만으로 전체를 설치/운영할 수 있도록 상세히 설명합니다.

## ✅ 빠른 시작

```bash
# 1) 가상환경 활성화 (권장) [[memory:3627098]]
source ~/env-blur/bin/activate

# 2) 환경파일(.env.streamN) 자동 생성
#    - generate_env.sh 상단에서 NUM_STREAMS, RTSP_URLS 배열을 필요에 맞게 수정 후 실행
./generate_env.sh

# 3) 전체 스트림과 파일 이동 서비스 실행
./start_all_streams.sh

# 4) 상태 확인
./status_all_streams.sh

# 5) 전체 중지
./stop_all_streams.sh
```

## 📦 구성 파일 개요

### Python 모듈
- `run.py`: 단일 스트림 런처. `.env`(혹은 프로세스 환경)로 설정을 로드하고, 수신/처리/저장 파이프라인을 실행합니다. 날짜별 로그 파일을 자동 회전 저장합니다.
- `config.py`: 환경변수 파싱과 설정 객체(`RTSPConfig`, `FFmpegConfig`, `OverlayConfig`)를 제공합니다. 파일명 생성과 GPS 포맷 유틸 포함.
- `stream_receiver.py`: OpenCV로 RTSP 프레임을 수신하여 큐로 전달. 재연결, FPS 페이싱, 수신 통계 관리.
- `frame_processor.py`: 큐에서 프레임을 읽어 YOLO 블러 적용, 1줄 오버레이 렌더링, 비디오 저장, SRT 갱신을 담당.
- `video_writer.py`: FFmpeg 파이프로 MP4 저장. `temp_` 접두사로 임시 저장 후 세그먼트 완료 시 최종명으로 rename. 날짜별 stderr 로깅.
- `subtitle_writer.py`: SRT 자막을 세그먼트 생명주기에 맞춰 초 단위 cue로 작성. 세그먼트 완료 시 `temp_` 제거.
- `blackbox_manager.py`: 블랙박스 API에서 주기적으로 GPS/속도 등을 가져와 오버레이/녹화 조건을 갱신.
- `api_client.py`: 블랙박스 API HTTP 클라이언트. 영상 완료 시 API로 메타데이터 전송(파일 크기는 MB 문자열로 전송).
- `monitor.py`: 시스템 리소스 모니터링(추후 Redis 연동 대비). 현재는 로컬 통계 수집.
- `file_mover.py`: watchdog으로 임시 디렉터리를 감시. `temp_*.mp4/.srt`가 최종명으로 바뀌면 시간 기반 경로(`/YYYY/MM/DD/HH/`)로 자동 이동하고, MP4는 API로 영상 정보를 전송합니다.

### Shell 스크립트
- `generate_env.sh`: 다중 스트림용 `.env.streamN` 파일들을 자동 생성. 스트림 수/URL, 출력 경로, 비트레이트 등 환경을 한 번에 정의.
- `start_all_streams.sh`: `.env.streamN`들을 기준으로 각 스트림을 개별 screen 세션으로 실행하고, 별도의 파일 이동 서비스 세션도 실행. 시간 동기화 screen 세션(주석 예시) 포함.
- `status_all_streams.sh`: 현재 실행 상태, 로그 파일 존재 여부와 크기 등을 요약 출력. 날짜 디렉터리 구조에 맞춰 로그 경로를 계산.
- `stop_all_streams.sh`: 실행 중인 스트림용 screen 세션과 파일 이동 서비스 세션을 중지하고, 임시 파일/임시 .env를 정리.

## ⚙️ generate_env.sh가 설정하는 환경변수

스크립트 상단에서 다음을 직접 수정하고 실행합니다.

- 스트림 수와 URL
  - `NUM_STREAMS`: 생성할 스트림 개수 (기본 6)
  - `RTSP_URLS`: 각 스트림의 RTSP URL 배열. 비워두거나 부족하면 `rtsp://<BASE_IP>:<START_PORT+i-1>/live` 규칙으로 자동 채움
- 출력/성능/블러/모니터링/API/녹화 조건
  - `TEMP_OUTPUT_PATH` (기본 `./output/temp/`): 임시 저장 디렉터리
  - `FINAL_OUTPUT_PATH` (기본 `/mnt/raid5/cam/`): 최종 저장 루트 디렉터리
  - `LOG_DIR` (기본 `/mnt/raid5/logs`): 공통 로그 디렉터리
  - `DEFAULT_INPUT_FPS` (기본 `15.0`)
  - `VIDEO_SEGMENT_DURATION` (기본 `300`초): 세그먼트 길이
  - `VIDEO_WIDTH`, `VIDEO_HEIGHT` (기본 `1920x1080`)
  - `DEFAULT_LATITUDE`, `DEFAULT_LONGITUDE`
  - `FRAME_QUEUE_SIZE` (기본 `100`), `CONNECTION_TIMEOUT` (기본 `10`), `RECONNECT_INTERVAL` (기본 `5`)
  - `ENABLE_MONITORING` (기본 `true`), `MONITORING_INTERVAL` (기본 `1.0`)
  - `BLUR_MODULE_PATH` (기본 제공 경로), `BLUR_ENABLED` (기본 `true`), `BLUR_CONFIDENCE` (기본 `0.5`)
  - `BLACKBOX_API_URL` (기본 `http://localhost`), `API_TIMEOUT` (기본 `5`), `API_POLL_INTERVAL` (기본 `1.0`), `BLACKBOX_ENABLED` (기본 `true`)
  - `RECORDING_SPEED_THRESHOLD` (기본 `5.0` knots): 속도 초과 시 저장 중단
- FFmpeg 비트레이트 (각 `.env.streamN`에 기록)
  - `FFMPEG_TARGET_BITRATE` (기본 `5M`), `FFMPEG_MIN_BITRATE` (기본 `1M`), `FFMPEG_MAX_BITRATE` (기본 `10M`)
- 로깅 (각 `.env.streamN`에 기록)
  - `LOG_LEVEL=INFO`, `LOG_ROTATION=on`, `LOG_ROTATE_INTERVAL=1`, `LOG_BACKUP_COUNT=7`

실행 결과: `.env.stream1` … `.env.streamN` 파일이 현재 디렉터리에 생성됩니다. 각 `.env.streamN`에는 해당 스트림의 `RTSP_URL`, `VESSEL_NAME`, `STREAM_NUMBER`, 출력/블러/모니터링/FFmpeg 관련 변수가 채워집니다.

## 🧰 start_all_streams.sh 동작 방식

- 사전 확인
  - `run.py` 존재, `screen` 설치 확인
  - `.env.streamN` 파일 존재 확인
  - 가상환경 `env-blur` 활성화 시도 [[memory:3627098]]
- 스트림 개수 감지
  - 우선순위: (1) 환경변수 `NUM_STREAMS` → (2) `.env.stream1`의 `NUM_STREAMS` → (3) 디렉터리 내 `.env.stream*` 최대 인덱스 → (4) 기본 6
- 로그 디렉터리 결정(상단 1회)
  - `.env.stream1`의 `LOG_DIR` → `.env.stream1`의 `FINAL_OUTPUT_PATH/logs` → `script_dir/logs`
- 각 스트림 실행(병렬 screen 세션)
  - 세션명: `rtsp_stream{i}`
  - `.env.stream{i}`를 `.env.temp{i}`로 복사하고, 임시 실행 스크립트를 생성하여 다음을 수행:
    - DOTENV_PATH를 `.env.temp{i}`로 설정
    - 실행 시점에 `ENV_FILE`에서 `LOG_DIR` 또는 `FINAL_OUTPUT_PATH/logs`를 읽어 날짜 디렉터리 구조(`YYYY/MM/DD/`)를 생성
    - `.env`로 복사 후 `python3 -u run.py` 실행
    - 표준출력은 당일 로그 파일 `logs/YYYY/MM/DD/rtsp_stream{i}_YYYYMMDD.log`로 기록(라인 단위 tee)
- 파일 이동 서비스 실행(별도 screen 세션)
  - 세션명: `rtsp_file_mover`
  - `.env.stream1`에서 `LOG_DIR` 또는 `FINAL_OUTPUT_PATH/logs`를 읽어 자체 로그(`file_mover_YYYYMMDD.log`)를 작성
  - watchdog으로 `TEMP_OUTPUT_PATH`를 감시하여 완료된 파일을 최종 경로(`/YYYY/MM/DD/HH/`)로 이동
  - MP4 이동 완료 시 블랙박스 API로 영상 정보를 전송(파일 크기는 MB 문자열)
- 시간 동기화(옵션, 주석 블록 제공)
  - `.env.stream1`의 `BLACKBOX_API_URL`을 읽어 서버 시간 동기화 screen 세션을 띄울 수 있는 주석 예시를 포함합니다.
  - 동기화 주기 설정: `TIME_SYNC_INTERVAL_SEC`(초). 우선순위: (1) 환경변수 → (2) `.env.stream1` → (3) 기본 300초
  - 주석 해제 예시(해당 스크립트 내):
    ```bash
    # screen -dmS bb_time_sync bash -lc 'BB_API="$(grep -E "^BLACKBOX_API_URL=" "$ENV_BASE_DIR/.env.stream1" | cut -d= -f2- | tr -d "\"")"; BB_API="${BB_API:-http://localhost}"; INTERVAL="${TIME_SYNC_INTERVAL_SEC:-}"; if [ -z "$INTERVAL" ]; then INTERVAL="$(grep -E "^TIME_SYNC_INTERVAL_SEC=" "$ENV_BASE_DIR/.env.stream1" | cut -d= -f2-)"; fi; INTERVAL="${INTERVAL:-300}"; while true; do dt=$(curl -sS "$BB_API/api/blackbox-logs/latest-gps" | jq -r ".payload.recordedDate"); if [ -n "$dt" ] && [ "$dt" != "null" ]; then sudo timedatectl set-ntp false; sudo timedatectl set-time "$dt"; sudo hwclock --systohc; fi; sleep "$INTERVAL"; done'
    ```

## 🔐 sudo 비밀번호 없이 시간 동기화 수행하기 (상세)

시간 동기화 screen 세션에서 `timedatectl`/`hwclock` 호출 시 매번 비밀번호 입력을 생략하려면 sudoers에 NOPASSWD 규칙을 추가합니다. 보안을 위해 필요한 커맨드만 최소 권한으로 허용합니다.

1) 명령 경로 확인
```bash
command -v timedatectl   # 보통 /usr/bin/timedatectl
command -v hwclock       # 보통 /sbin/hwclock (또는 /usr/sbin/hwclock)
```

2) 안전한 편집 실행
```bash
sudo visudo
```

3) 아래 항목을 사용자에 맞게 추가(예: 사용자명이 koast-user)
```text
koast-user ALL=(ALL) NOPASSWD: \
  /usr/bin/timedatectl set-ntp false, \
  /usr/bin/timedatectl set-time *, \
  /sbin/hwclock --systohc
```
- `set-time`은 인자(날짜/시간 문자열)가 필요하므로 `set-time *`로 허용합니다.
- `hwclock` 경로는 시스템에 따라 `/sbin/hwclock` 혹은 `/usr/sbin/hwclock`일 수 있습니다.

4) 적용 확인
```bash
sudo -l | grep -E 'timedatectl|hwclock' | cat
sudo timedatectl set-ntp false
sudo timedatectl set-time "2025-01-01 00:00:00"
sudo hwclock --systohc
```
- 비밀번호 프롬프트가 나타나지 않으면 성공입니다.

5) 주기 설정과 함께 실행(예시)
```bash
# 환경변수로 10분(600초) 주기 지정 후 시작 스크립트 실행
export TIME_SYNC_INTERVAL_SEC=600
./start_all_streams.sh
```

기타 주의사항
- `recordedDate`가 타임존 정보 없이 로컬 시간이라 가정합니다. 필요 시 먼저 서버 타임존을 설정하세요.
- NTP가 켜져 있으면 수동 설정이 덮일 수 있으므로 동기화 직전에 `timedatectl set-ntp false`를 사용합니다. 이후 자동 동기화로 되돌리려면 `timedatectl set-ntp true`를 수동으로 켤 수 있습니다.

## 🛑 stop_all_streams.sh 동작 방식

현재 스크립트는 고정 6개 세션을 대상으로 동작합니다(개선 예정).

- screen 세션 중지
  - `rtsp_stream1..6` 세션과 `rtsp_file_mover` 세션을 순차 종료
- 임시 파일 처리 및 정리
  - `profiles/$PROFILE/.env.stream{i}`를 참고하여 각 스트림의 `TEMP_OUTPUT_PATH`에서 `temp_*.mp4`를 최종명으로 rename(파일 이동기가 처리하도록 유도)
  - `.env.temp1..6`와 임시 `.env` 파일 삭제
- 결과 요약 출력
  - 중지된 세션 수와 정리된 임시 파일 수를 출력

참고: `start_all_streams.sh`, `status_all_streams.sh`는 프로필 의존성을 제거했으나, `stop_all_streams.sh`는 아직 프로필 경로를 사용합니다. 필요 시 동일한 규칙으로 개선할 수 있습니다.

## 🔎 status_all_streams.sh 동작 방식

- `.env.stream1`에서 `LOG_DIR` 또는 `FINAL_OUTPUT_PATH/logs`를 읽어 `LOGS_DIR` 계산
- 각 스트림에 대해:
  - screen 세션 실행 여부
  - 설정 파일(`.env.stream{i}`) 존재 여부
  - 날짜 디렉토리(`$LOGS_DIR/YYYY/MM/DD/`) 하위의 당일 로그 존재 여부, 크기, 라인 수, 수정 시각, 마지막 라인 에러 키워드 검사

## 🧩 주요 실행 흐름(단일 스트림)

1) `run.py`가 `.env`를 로드 → `RTSPConfig.from_env()`로 설정 구성 → 유효성 검증
2) `StreamReceiver`: RTSP 수신, FPS 제어, 재연결, 통계
3) `FrameProcessor`: YOLO 블러 → 오버레이 → `VideoWriterManager.write_frame()` 순서로 처리
4) `VideoWriterManager`: `temp_*.mp4`로 기록 → 세그먼트 완료 시 최종명으로 rename → 요약 로그 출력 → SRT finalize 콜백 호출
5) `file_mover.py`(별도 세션): temp 제거 감지 시 최종 경로로 이동하고, 블랙박스 API로 메타데이터 전송(파일 크기 MB 문자열)

## 🌐 블랙박스 API 연동

- 위치/속도 폴링: `GET /api/blackbox-logs/latest-gps`
  - 응답의 `payload.recordedDate`가 있으면 오버레이 시간으로 사용
- 영상 메타 전송: `POST /api/camera-videos`
  - 필드: `cameraId`, `cameraName`, `vesselId`, `vesselName`, `gearCode`, `gearName`, `gearNameKo`, `fileName`, `fileRealName`, `filePath`, `fileSize`(MB 문자열), `fileExt`, `recordStartTime`, `recordEndTime`
  - 파일 크기는 바이트가 아닌 MB 문자열(예: `"12.34"`)로 전송됨

## 📝 운영 팁

- 로그 위치 요약
  - 실행 로그: `LOG_DIR/YYYY/MM/DD/rtsp_stream{i}_YYYYMMDD.log`
  - FFmpeg stderr: `LOG_DIR/YYYY/MM/DD/ffmpeg_writer_stream{i}_YYYYMMDD.stderr.log`
  - 파일 이동 서비스: `LOG_DIR/YYYY/MM/DD/file_mover_YYYYMMDD.log`
- 세그먼트 길이: `VIDEO_SEGMENT_DURATION`(초)로 제어. 기본 300초(5분)
- 시간 동기화(옵션)
  - screen 세션 주석 해제 또는 systemd timer/cron으로 주기 동기화 가능
  - NTP가 켜져 있으면 동기화 직전에 `timedatectl set-ntp false` 수행

## 🛠️ 트러블슈팅

- RTSP 연결 실패
  - 카메라 접근/네트워크 확인, URL 점검, 방화벽 확인
- 파일 이동이 안 됨
  - `TEMP_OUTPUT_PATH`와 `FINAL_OUTPUT_PATH` 권한/경로 확인, `file_mover` 세션 로그 확인
- 로그가 안 쌓임
  - `.env.stream1`의 `LOG_DIR`/`FINAL_OUTPUT_PATH` 확인, 날짜 디렉터리 구조 하위 파일 확인
- API 전송 실패
  - `BLACKBOX_API_URL` 확인, 서버 응답 로그 확인, 파일 크기(MB 문자열) 변환 로직은 `api_client.py` 참고

## 📋 환경변수 참고(추가)

- FFmpeg 세부 설정(선택): `FFMPEG_VIDEO_CODEC`, `FFMPEG_COMPRESSION_LEVEL`, `FFMPEG_QUALITY_MODE`, `FFMPEG_INPUT_FPS`, `FFMPEG_OUTPUT_FPS`, `FFMPEG_KEYINT`, `FFMPEG_CONTAINER`, `FFMPEG_PIXEL_FORMAT`, `FFMPEG_PRESET`, `FFMPEG_TUNE`, `FFMPEG_PROFILE`, `FFMPEG_LEVEL`, `FFMPEG_BUFFER_SIZE`, `FFMPEG_VSYNC`, `FFMPEG_LOGLEVEL`, `FFMPEG_HWACCEL`
- 로깅: `LOG_FILE`, `FILE_LOG_LEVEL`, `PY_LOG_TO_FILE`
- 수신 최적화: `RECEIVER_PACING`(true/false)

## 📄 라이선스

MIT License 