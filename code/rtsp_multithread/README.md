# RTSP Multithread Processor

단일 RTSP 스트림을 2개 스레드로 처리하여 YOLO 머리 감지, 블러 처리, MP4 저장을 수행하는 모듈화된 패키지입니다.

## 🎯 주요 기능

- **단일 스트림 처리**: 1개의 RTSP 스트림만 처리 (멀티 프로세스 지원)
- **2개 스레드 구조**: 스트림 수신 + 프레임 처리/저장
- **YOLO 블러 처리**: 사용자 정의 YOLO 모듈로 머리 감지 및 블러
- **임시 파일 관리**: `temp_` 접두사로 저장 중 표시, 완료 시 정식 파일명
- **자동 파일 이동**: watchdog 기반 완료된 영상 파일 자동 최종 경로 이동
- **시간 기반 저장**: `/mnt/raid5/YYYY/MM/DD/HH/` 계층 구조 자동 생성
- **15fps VBR 최적화**: 해상망 환경에 최적화된 FFmpeg 설정
- **1줄 오버레이**: 선박명, 스트림번호, GPS(60분법), 시간 표시 (초단위 포함)
- **리소스 모니터링**: Redis 연동 준비된 시스템 모니터링
- **환경변수 설정**: 유연한 설정 관리

## 📁 모듈 구조

```
rtsp_multithread/
├── __init__.py          # 패키지 초기화
├── config.py            # 설정 관리 (환경변수, FFmpeg, 오버레이)
├── stream_receiver.py   # RTSP 스트림 수신 스레드
├── frame_processor.py   # 프레임 처리 및 저장 스레드
├── blur_handler.py      # YOLO 블러 모듈 인터페이스
├── video_writer.py      # FFmpeg 기반 MP4 저장 관리
├── monitor.py           # 시스템 리소스 모니터링 (Redis 준비)
├── file_mover.py        # watchdog 기반 파일 자동 이동 서비스
├── main.py              # 메인 실행 모듈
├── run_example.py       # 사용 예제
└── README.md           # 이 파일
```

## 🚀 빠른 시작

```bash
# .env 파일들 자동 생성
./generate_env.sh

# 6개 스트림 + 파일 이동 서비스 시작
./start_all_streams.sh

# 전체 상태 확인
./status_all_streams.sh

# 전체 중지
./stop_all_streams.sh
```


## ⚙️ 설정 옵션

### 환경변수

| 변수명 | 기본값 | 설명 |
|--------|--------|------|
| `RTSP_URL` | - | RTSP 스트림 URL (필수) |
| `VESSEL_NAME` | DEFAULT_VESSEL | 선박 이름 |
| `STREAM_NUMBER` | 1 | 스트림 번호 |
| `BLUR_MODULE_PATH` | None | YOLO 블러 모듈 경로 |
| `TEMP_OUTPUT_PATH` | ./output/temp/ | 임시 파일 저장 경로 |
| `FINAL_OUTPUT_PATH` | /mnt/raid5 | 최종 파일 저장 경로 |
| `DEFAULT_LATITUDE` | 37.5665 | 기본 위도 (서울) |
| `DEFAULT_LONGITUDE` | 126.9780 | 기본 경도 (서울) |
| `BLUR_ENABLED` | True | 블러 처리 활성화 |
| `FRAME_QUEUE_SIZE` | 100 | 프레임 큐 크기 |
| `ENABLE_MONITORING` | True | 리소스 모니터링 |

### FFmpeg 설정 (15fps VBR 최적화)

```python
ffmpeg_config = FFmpegConfig(
    video_codec="libx264",      # H.264 코덱
    quality_mode="vbr",         # VBR 모드
    target_bitrate="2M",        # 목표 2Mbps
    min_bitrate="1M",           # 최소 1Mbps
    max_bitrate="4M",           # 최대 4Mbps
    input_fps=15.0,             # 15fps 고정
    preset="medium",            # 중간 속도
    tune="film",                # 일반 영상 최적화
)
```

## 🎬 출력 파일 형식

### 파일명 형식
```
{배이름}_{스트림번호}_{YYMMDD}_{HHMMSS}.mp4
```

### 예시
```
vesselTest_stream01_241201_143052.mp4
```

### 임시 파일 처리
- 저장 중: `temp_vesselTest01_01_241201_143052.mp4` (임시 경로)
- 완료 후: `vesselTest01_01_241201_143052.mp4` (임시 경로)
- 자동 이동: `vesselTest01_01_241201_143052.mp4` (최종 경로)

### 자동 파일 이동 시스템
- **watchdog 기반**: temp_ 접두사 제거 감지 시 자동 이동
- **시간 기반 경로**: 파일명에서 시간 추출하여 `/YYYY/MM/DD/HH/` 구조 생성
- **원자적 이동**: shutil.move로 안전한 파일 이동
- **별도 프로세스**: 파일 이동 서비스가 독립적으로 실행

## 📊 오버레이 표시

영상 상단 좌측에 1줄로 표시:

```
SHIP_KOREA_01 | S01 | 037°33'59.4"N 126°58'40.8"E | 241201 14:30
```

- **선박명**: 최대 12자
- **스트림 번호**: S01, S02, ...
- **GPS 좌표**: 60분법 (도분초)
- **시간**: YYMMDD HH:MM

## 🔧 YOLO 블러 모듈 연동

### 사용자 모듈 인터페이스

```python
# your_blur_module.py
class HeadBlurrer:
    def __init__(self):
        # YOLO 모델 초기화
        pass
    
    def process_frame(self, frame):
        # 머리 감지 및 블러 처리
        # return 블러 처리된 프레임
        return frame
```

### 환경변수 설정
```bash
export BLUR_MODULE_PATH='/path/to/your_blur_module.py'
```

## 📈 모니터링 및 통계

### 실시간 통계
- 프레임 수신/처리/저장 통계
- 큐 상태 모니터링
- 시스템 리소스 사용량 (CPU, 메모리, GPU)

### Redis 연동 준비
```python
# TODO: 향후 구현 예정
# Redis 키 구조:
# rtsp_monitor:{hostname}:current → 현재 상태
# rtsp_monitor:{hostname}:history:{timestamp} → 히스토리
```

## 🐳 Docker 실행 (선택사항)

```dockerfile
FROM python:3.9

# FFmpeg 설치
RUN apt-get update && apt-get install -y ffmpeg

# 패키지 설치
COPY requirements.txt .
RUN pip install -r requirements.txt

# 코드 복사
COPY rtsp_multithread/ /app/rtsp_multithread/
WORKDIR /app

# 실행
CMD ["python", "-m", "rtsp_multithread.main"]
```

```bash
# 빌드 및 실행
docker build -t rtsp-processor .
docker run -e RTSP_URL='rtsp://camera-ip:554/stream' \
           -v ./output:/app/output \
           rtsp-processor
```

## 📋 요구사항

### 시스템 요구사항
- Python 3.8+
- FFmpeg
- OpenCV
- 최소 2GB RAM
- 15fps 실시간 처리를 위한 적절한 CPU

### Python 패키지
```bash
pip install opencv-python numpy psutil python-dotenv
```

### 선택적 패키지
```bash
# GPU 모니터링
pip install gputil

# YOLO 모델 사용 시
pip install torch torchvision ultralytics
```

## 🔍 문제 해결

### 일반적인 문제

1. **FFmpeg 오류**
   ```bash
   # Ubuntu/Debian
   sudo apt install ffmpeg
   
   # CentOS/RHEL
   sudo yum install ffmpeg
   ```

2. **RTSP 연결 실패**
   - 네트워크 연결 확인
   - RTSP URL 정확성 확인
   - 방화벽 설정 확인

3. **블러 모듈 로드 실패**
   - 모듈 경로 확인
   - HeadBlurrer 클래스 존재 확인
   - 의존성 패키지 설치 확인

### 로그 확인
```bash
# 실행 로그
tail -f rtsp_processor.log

# 상세 디버그 로그
export PYTHONPATH=$PYTHONPATH:/path/to/rtsp_multithread
python -c "import logging; logging.basicConfig(level=logging.DEBUG)"
```

## 🤝 향후 개발 계획

- [ ] Redis 연동 구현
- [ ] 웹 대시보드 추가
- [ ] 멀티 스트림 매니저
- [ ] 성능 최적화
- [ ] Docker Compose 설정
- [ ] Kubernetes 배포 가이드

## 📄 라이선스

MIT License

## 👥 기여자

RTSP Team 