#!/bin/bash

# RTSP 스트림 테스트 스크립트
# 6개의 MediaMTX 스트림에 대해 각각 5초간 패킷 손실률 분석

echo "=== 6개 RTSP 스트림 패킷 손실률 테스트 ==="
echo "각 스트림에 대해 5초간 분석합니다..."
echo

for i in {1..6}; do
    port=$((1110 + i))
    stream_name="스트림 $i"
    url="rtsp://10.2.10.158:$port/live"
    
    echo "[$i/6] $stream_name 테스트 중... ($url)"
    echo "----------------------------------------"
    
    python3 rtsp_client_packet_analyzer.py --url "$url" --duration 5
    
    echo
    echo "=========================================="
    echo
    
    # 스트림 간 간격
    sleep 1
done

echo "전체 테스트 완료!"