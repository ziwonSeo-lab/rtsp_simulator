# 사용 예제 및 테스트

## 🎥 로컬 영상 및 RTSP 혼합 사용

### 1. 설정 파일 예제

#### `rtsp_recorder_config.json`
```json
{
  "sources": [
    "rtsp://admin:password@192.168.1.100:554/stream",
    "./videos/sample_video1.mp4",
    "./videos/sample_video2.mp4",
    "rtsp://192.168.1.101:554/live"
  ],
  "output_dir": "./raw_videos",
  "queue_dir": "./processing_queue",
  "segment_duration": 30,
  "input_fps": 15.0,
  "max_concurrent_recordings": 4,
  "enable_monitoring": true,
  "monitoring_interval": 10
}
```

### 2. 테스트 영상 준비

```bash
# 테스트 영상 다운로드 (예시)
mkdir -p ./videos
wget -O ./videos/sample_video1.mp4 "https://sample-videos.com/zip/10/mp4/SampleVideo_1280x720_1mb.mp4"
wget -O ./videos/sample_video2.mp4 "https://sample-videos.com/zip/10/mp4/SampleVideo_1280x720_2mb.mp4"

# 또는 직접 영상 생성 (FFmpeg 사용)
ffmpeg -f lavfi -i testsrc=duration=60:size=1280x720:rate=30 -c:v libx264 ./videos/test_pattern.mp4
```

### 3. 시스템 실행

```bash
# 1. 기본 설정 생성
python run_system.py --create-configs

# 2. 설정 파일 수정 (sources 부분을 실제 경로로 변경)
nano rtsp_recorder_config.json

# 3. 시스템 실행
python run_system.py
```

## 🔧 개별 컴포넌트 테스트

### RTSP 녹화 프로세스만 테스트

```bash
# 설정 파일 생성
python rtsp_recorder.py --create-config

# 녹화 시작
python rtsp_recorder.py --config rtsp_recorder_config.json
```

### 블러 처리 프로세스만 테스트

```bash
# 설정 파일 생성
python blur_processor.py --create-config

# 블러 처리 시작
python blur_processor.py --config blur_processor_config.json
```

### 블러 모듈 테스트

```bash
# 예제 블러 모듈 테스트
python example_blur_module.py
```

## 📊 모니터링 및 로그 확인

### 실시간 로그 확인

```bash
# 시스템 전체 로그
python run_system.py 2>&1 | tee system.log

# 특정 프로세스 로그 필터링
python run_system.py 2>&1 | grep "RECORDER"
python run_system.py 2>&1 | grep "BLUR_PROCESSOR"
```

### 큐 상태 확인

```bash
# 처리 대기 큐 파일 수 확인
ls -la ./processing_queue/queue_*.json | wc -l

# 큐 파일 내용 확인
cat ./processing_queue/queue_*.json | head -1 | jq .
```

### 저장된 파일 확인

```bash
# 원본 영상 파일
find ./raw_videos -name "*.mp4" -exec ls -lh {} \;

# 처리된 영상 파일
find ./processed_videos -name "*.mp4" -exec ls -lh {} \;
```

## 🎯 성능 테스트

### 부하 테스트 스크립트

```bash
#!/bin/bash
# test_load.sh

echo "=== 시스템 부하 테스트 ==="

# 1. 시스템 리소스 확인
echo "1. 시스템 리소스:"
free -h
df -h
lscpu | grep "CPU(s)"

# 2. 테스트 영상 생성
echo "2. 테스트 영상 생성:"
mkdir -p ./test_videos
for i in {1..5}; do
    if [ ! -f "./test_videos/test_video_$i.mp4" ]; then
        ffmpeg -f lavfi -i testsrc=duration=120:size=1280x720:rate=30 \
               -c:v libx264 -preset fast -crf 23 \
               ./test_videos/test_video_$i.mp4
    fi
done

# 3. 설정 파일 생성
echo "3. 테스트 설정 생성:"
python3 -c "
import json
config = {
    'sources': [f'./test_videos/test_video_{i}.mp4' for i in range(1, 6)],
    'output_dir': './test_raw_videos',
    'queue_dir': './test_processing_queue',
    'segment_duration': 10,
    'input_fps': 15.0,
    'max_concurrent_recordings': 4,
    'enable_monitoring': True,
    'monitoring_interval': 5
}
with open('test_recorder_config.json', 'w') as f:
    json.dump(config, f, indent=2)
"

# 4. 시스템 실행 (5분간)
echo "4. 시스템 실행 (5분간):"
timeout 300 python run_system.py \
    --recorder-config test_recorder_config.json \
    --blur-config blur_processor_config.json

# 5. 결과 확인
echo "5. 테스트 결과:"
echo "원본 파일 수: $(find ./test_raw_videos -name '*.mp4' | wc -l)"
echo "처리된 파일 수: $(find ./processed_videos -name '*.mp4' | wc -l)"
echo "큐 대기 파일 수: $(find ./test_processing_queue -name '*.json' | wc -l)"
```

### 성능 벤치마크

```python
#!/usr/bin/env python3
# benchmark.py

import time
import psutil
import os
import json
from pathlib import Path

def benchmark_system():
    """시스템 성능 벤치마크"""
    
    print("=== 시스템 성능 벤치마크 ===")
    
    # 시스템 정보
    print(f"CPU 코어: {psutil.cpu_count()}")
    print(f"메모리: {psutil.virtual_memory().total / 1024**3:.1f}GB")
    print(f"디스크: {psutil.disk_usage('.').total / 1024**3:.1f}GB")
    
    # 테스트 시간
    test_duration = 60  # 1분
    start_time = time.time()
    
    # 초기 파일 수
    raw_files_start = len(list(Path("./raw_videos").rglob("*.mp4"))) if Path("./raw_videos").exists() else 0
    processed_files_start = len(list(Path("./processed_videos").rglob("*.mp4"))) if Path("./processed_videos").exists() else 0
    
    print(f"\n테스트 시작 - {test_duration}초간 실행")
    print(f"초기 파일 수 - 원본: {raw_files_start}, 처리: {processed_files_start}")
    
    # 시스템 실행 (백그라운드)
    import subprocess
    process = subprocess.Popen(
        ["python", "run_system.py", "--duration", str(test_duration)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # 모니터링
    cpu_usage = []
    memory_usage = []
    
    while process.poll() is None:
        cpu_usage.append(psutil.cpu_percent(interval=1))
        memory_usage.append(psutil.virtual_memory().percent)
        
        if time.time() - start_time > test_duration + 10:
            break
    
    process.wait()
    
    # 최종 파일 수
    raw_files_end = len(list(Path("./raw_videos").rglob("*.mp4"))) if Path("./raw_videos").exists() else 0
    processed_files_end = len(list(Path("./processed_videos").rglob("*.mp4"))) if Path("./processed_videos").exists() else 0
    
    # 결과 출력
    print(f"\n=== 벤치마크 결과 ===")
    print(f"테스트 시간: {test_duration}초")
    print(f"생성된 원본 파일: {raw_files_end - raw_files_start}")
    print(f"처리된 파일: {processed_files_end - processed_files_start}")
    print(f"평균 CPU 사용률: {sum(cpu_usage)/len(cpu_usage):.1f}%")
    print(f"최대 CPU 사용률: {max(cpu_usage):.1f}%")
    print(f"평균 메모리 사용률: {sum(memory_usage)/len(memory_usage):.1f}%")
    print(f"최대 메모리 사용률: {max(memory_usage):.1f}%")
    
    # 처리율 계산
    if raw_files_end > raw_files_start:
        processing_rate = (processed_files_end - processed_files_start) / (raw_files_end - raw_files_start) * 100
        print(f"처리율: {processing_rate:.1f}%")

if __name__ == "__main__":
    benchmark_system()
```

## 🐛 문제 해결

### 일반적인 문제들

1. **로컬 영상 파일을 찾을 수 없음**
```bash
# 파일 경로 확인
ls -la ./videos/

# 절대 경로 사용
python -c "import os; print(os.path.abspath('./videos/sample.mp4'))"
```

2. **RTSP 연결 실패**
```bash
# RTSP 스트림 테스트
ffplay rtsp://your-rtsp-url

# 네트워크 연결 확인
ping 192.168.1.100
telnet 192.168.1.100 554
```

3. **처리 속도 느림**
```bash
# 프로세스 수 증가
# blur_processor_config.json에서
{
  "max_concurrent_processes": 4  # 기본값 2에서 증가
}

# 세그먼트 길이 줄이기
# rtsp_recorder_config.json에서
{
  "segment_duration": 10  # 기본값 30에서 감소
}
```

4. **디스크 공간 부족**
```bash
# 디스크 사용량 확인
du -sh ./raw_videos ./processed_videos

# 자동 정리 활성화
# blur_processor_config.json에서
{
  "delete_original": true,
  "backup_original": false
}
```

### 로그 분석

```bash
# 오류 로그 확인
python run_system.py 2>&1 | grep -i error

# 성능 로그 확인
python run_system.py 2>&1 | grep -i "fps\|처리율\|통계"

# 특정 소스 로그 확인
python run_system.py 2>&1 | grep "source_name"
```

## 🚀 최적화 팁

### 1. 하드웨어 최적화
- **CPU**: 코어 수만큼 동시 처리 프로세스 설정
- **메모리**: 8GB 이상 권장
- **디스크**: SSD 사용 시 성능 향상

### 2. 소프트웨어 최적화
- **FFmpeg**: 하드웨어 가속 사용
- **OpenCV**: 최신 버전 사용
- **Python**: 멀티프로세싱 활용

### 3. 네트워크 최적화
- **대역폭**: 충분한 네트워크 대역폭 확보
- **지연시간**: 낮은 지연시간 네트워크 사용
- **연결 안정성**: 유선 연결 권장

이제 **로컬 영상 파일과 RTSP 카메라를 자유롭게 조합**하여 사용할 수 있습니다! 🎉