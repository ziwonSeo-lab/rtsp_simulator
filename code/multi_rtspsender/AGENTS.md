<!-- Parent: ../AGENTS.md -->
# multi_rtspsender - 멀티 RTSP 송신 모듈

## Purpose

여러 비디오 파일을 RTSP 스트림으로 동시 송신하는 모듈입니다. FFmpeg과 MediaMTX를 활용하여 RTMP → RTSP 변환을 수행합니다.

## Key Files

- `README.md` - 실행 가이드 (필독)

## Subdirectories

- `src/` - 소스 코드
  - `server/rtsp_sender.py` - RTSP 송신 서버
  - `client/` - 클라이언트 코드
  - `analysis/` - 분석 도구
- `config/` - 설정 파일
  - `config_noloss.json` - 무손실 설정
  - `mediamtx/` - MediaMTX 설정
  - `network/` - 네트워크 설정
- `scripts/` - 관리 스크립트
  - `management/` - MediaMTX 시작/중지
  - `setup/` - 초기 설정
- `tools/` - 유틸리티 도구
  - `udp/` - UDP 도구
  - `utils/` - 유틸리티
- `docs/` - 문서
- `logs/` - 로그 파일
- `tests/` - 테스트
  - `integration/` - 통합 테스트
  - `unit/` - 유닛 테스트

## For AI Agents

### 실행 순서

```bash
# 1. MediaMTX 시작
cd scripts/management
bash start_all_mediamtx.sh

# 2. RTSP 송신 시작
cd ../..
nohup sudo python3 src/server/rtsp_sender.py -c config/config_noloss.json 2>&1 &

# 3. 프로세스 확인
ps -ef | grep rtsp_sender.py
```

### 데이터 흐름

```
비디오 파일 (1920x1080)
  ↓ FFmpeg concat
RTMP → localhost:1911-1916
  ↓ MediaMTX
RTSP → 10.2.10.158:1111-1116
```

### 설정 파일 구조 (config_noloss.json)

```json
{
  "streams": [
    {
      "video_files": ["/path/to/video1.mp4", "/path/to/video2.mp4"],
      "rtmp_port": 1911,
      "rtsp_port": 1111
    }
  ]
}
```

### MediaMTX 관리

```bash
# 시작
bash scripts/management/start_all_mediamtx.sh

# 중지
bash scripts/management/stop_all_mediamtx.sh

# 프로세스 확인
ps -ef | grep mediamtx
```

## Dependencies

- FFmpeg
- MediaMTX
- Python 3.7+
