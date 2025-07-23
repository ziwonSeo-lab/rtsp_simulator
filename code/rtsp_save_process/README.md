# RTSP 영상 처리 시스템

독립적인 2개 프로세스로 구성된 RTSP 영상 저장 및 블러 처리 시스템입니다.

⚡ 핵심 특징
✅ 독립적 동작

RTSP 저장이 계속 진행되면서 블러 처리도 동시에 실행
한 프로세스가 중단되어도 다른 프로세스는 계속 동작

✅ 큐 기반 연결

저장 완료된 파일을 JSON 큐 파일로 전달
블러 처리 프로세스가 큐를 폴링하여 처리

✅ 자동 파일 관리

블러 처리 완료 후 원본 파일 자동 삭제
백업 옵션 지원

✅ 확장성

여러 RTSP 스트림 동시 처리
블러 처리 프로세스 다중 실행 가능

## 🏗️ 시스템 구조

```
📹 RTSP 스트림 입력
    ↓
🔴 RTSP 녹화 프로세스 (rtsp_recorder.py)
    ↓ [processing_queue]
🎨 블러 처리 프로세스 (blur_processor.py)
    ↓
💾 최종 블러 처리된 영상
```

## 📁 파일 구조

```
rtsp_processing_system/
├── rtsp_recorder.py              # RTSP 녹화 프로세스
├── blur_processor.py             # 블러 처리 프로세스
├── run_system.py                 # 시스템 실행 스크립트
├── example_blur_module.py        # 예제 블러 모듈
├── rtsp_recorder_config.json     # 녹화 설정
├── blur_processor_config.json    # 블러 처리 설정
├── raw_videos/                   # 원본 영상 저장
├── processed_videos/             # 처리된 영상 저장
├── processing_queue/             # 처리 대기 큐
└── logs/                         # 로그 파일
```

## 🚀 빠른 시작

### 1. 시스템 설정

```bash
# 기본 설정 파일 생성
python run_system.py --create-configs

# 시스템 검증
python run_system.py --validate
```

### 2. 설정 파일 수정

#### RTSP 녹화 설정 (`rtsp_recorder_config.json`)
```json
{
  "sources": [
    "rtsp://admin:password@192.168.1.100:554/stream",
    "rtsp://admin:password@192.168.1.101:554/stream"
  ],
  "segment_duration": 30,
  "input_fps": 15.0,
  "max_concurrent_recordings": 4
}
```

#### 블러 처리 설정 (`blur_processor_config.json`)
```json
{
  "blur_module_path": "./example_blur_module.py",
  "max_concurrent_processes": 2,
  "delete_original": true,
  "add_overlay": true
}
```

### 3. 시스템 실행

```bash
# 전체 시스템 실행
python run_system.py

# 30분 동안만 실행
python run_system.py --duration 1800
```

## 🔧 개별 프로세스 실행

### RTSP 녹화 프로세스만 실행
```bash
# 기본 설정으로 실행
python rtsp_recorder.py

# 커스텀 설정으로 실행
python rtsp_recorder.py --config my_recorder_config.json
```

### 블러 처리 프로세스만 실행
```bash
# 기본 설정으로 실행
python blur_processor.py

# 커스텀 설정으로 실행
python blur_processor.py --config my_blur_config.json
```

## 🎨 블러 모듈 개발

### 기본 인터페이스

```python
# 방법 1: HeadBlurrer 클래스
class HeadBlurrer:
    def __init__(self, num_camera=1):
        pass
    
    def process_frame(self, frame, camera_index=0):
        # 블러 처리 로직
        return processed_frame

# 방법 2: apply_blur 함수
def apply_blur(frame, thread_id=0):
    # 블러 처리 로직
    return processed_frame
```

### 예제 블러 모듈 사용
```python
# example_blur_module.py 테스트
python example_blur_module.py
```

## 📊 모니터링 및 로그

### 시스템 상태 모니터링
- 실시간 프로세스 상태
- CPU/메모리 사용량
- 처리 대기 큐 크기
- 저장 용량 정보

### 로그 파일 위치
```
logs/
├── rtsp_recorder.log    # 녹화 로그
├── blur_processor.log   # 블러 처리 로그
└── system.log           # 시스템 로그
```

## ⚙️ 주요 기능

### RTSP 녹화 프로세스
- **다중 스트림 지원**: 여러 RTSP 스트림 동시 녹화
- **세그먼트 기반 저장**: 설정한 시간 간격으로 파일 분할
- **자동 재연결**: 연결 끊김 시 자동 재연결
- **실시간 모니터링**: 녹화 상태 및 통계 정보

### 블러 처리 프로세스
- **큐 기반 처리**: 저장 완료된 파일 순차 처리
- **다중 프로세스**: 여러 파일 동시 처리
- **사용자 블러 모듈**: 커스텀 블러 알고리즘 지원
- **자동 파일 정리**: 처리 완료 후 원본 파일 삭제

## 🛠️ 고급 설정

### 성능 최적화
```json
{
  "max_concurrent_recordings": 4,     // CPU 코어 수에 맞춤
  "max_concurrent_processes": 2,      // GPU 성능에 맞춤
  "segment_duration": 30,             // 짧을수록 빠른 처리
  "polling_interval": 1.0             // 큐 확인 간격
}
```

### 디스크 관리
```json
{
  "max_disk_usage_gb": 100.0,         // 최대 디스크 사용량
  "cleanup_old_files": true,          // 오래된 파일 자동 정리
  "max_file_age_hours": 24,           // 파일 보관 시간
  "backup_original": false            // 원본 파일 백업 여부
}
```

### 영상 품질 설정
```json
{
  "input_fps": 15.0,                  // 입력 FPS
  "video_codec": "libx264",           // 비디오 코덱
  "bitrate": "2M",                    // 비트레이트
  "resize_before_blur": false,        // 블러 전 리사이즈
  "blur_strength": 15                 // 블러 강도
}
```

## 🔍 문제 해결

### 일반적인 문제

1. **RTSP 연결 실패**
   - 네트워크 연결 확인
   - 인증 정보 확인
   - 방화벽 설정 확인

2. **블러 처리 오류**
   - 블러 모듈 경로 확인
   - Python 패키지 설치 확인
   - 메모리 사용량 확인

3. **디스크 공간 부족**
   - 최대 디스크 사용량 설정
   - 자동 정리 기능 활성화
   - 세그먼트 길이 조정

### 로그 확인
```bash
# 실시간 로그 확인
tail -f logs/system.log

# 특정 프로세스 로그 확인
grep "ERROR" logs/rtsp_recorder.log
```

## 📈 성능 지표

### 권장 하드웨어
- **CPU**: 4코어 이상
- **메모리**: 8GB 이상
- **디스크**: SSD 권장
- **네트워크**: 안정적인 연결

### 성능 벤치마크
- **동시 녹화**: 4개 스트림 (1080p@15fps)
- **블러 처리**: 2개 프로세스 동시 처리
- **처리 속도**: 실시간 기준 1.5배 이상

## 🤝 확장 가능성

### 추가 기능 구현
- 객체 검출 및 추적
- 동작 감지
- 알림 시스템
- 웹 대시보드
- 클라우드 연동

### API 연동
```python
# 외부 API 호출 예제
import requests

def send_notification(message):
    requests.post('https://api.example.com/notify', 
                  json={'message': message})
```

## 📝 라이선스

이 시스템은 MIT 라이선스하에 배포됩니다.

## 📞 지원

문제가 발생하거나 개선사항이 있으시면 이슈를 생성해주세요.