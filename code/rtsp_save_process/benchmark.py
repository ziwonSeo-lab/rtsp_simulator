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