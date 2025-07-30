#!/usr/bin/env python3
"""
실시간 통계 모니터링 스크립트
"""

import sys
import os
import time
import json

# 현재 디렉토리를 Python path에 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

def print_stats_header():
    """통계 헤더 출력"""
    print("\n" + "="*80)
    print("📊 RTSP 프레임/패킷 손실 통계")
    print("="*80)
    print(f"{'시간':>8} {'스트림':>10} {'수신':>8} {'처리':>8} {'저장':>8} {'손실':>8} {'에러':>8} {'손실률':>8}")
    print("-"*80)

def format_stats_line(timestamp, stream_id, stats):
    """통계 라인 포맷"""
    received = stats.get('received_frames', 0)
    processed = stats.get('processed_frames', 0) 
    saved = stats.get('saved_frames', 0)
    lost = stats.get('lost_frames', 0)
    errors = stats.get('error_frames', 0)
    loss_rate = stats.get('loss_rate', 0.0)
    
    return f"{timestamp:>8} {stream_id:>10} {received:>8} {processed:>8} {saved:>8} {lost:>8} {errors:>8} {loss_rate:>7.1f}%"

def monitor_stats():
    """통계 모니터링"""
    try:
        from rtsp_client_module.statistics import FrameStatistics
        
        print_stats_header()
        
        # 가상의 통계 데이터 (실제로는 SharedPoolRTSPProcessor에서 가져와야 함)
        counter = 0
        while True:
            counter += 1
            timestamp = time.strftime("%H:%M:%S")
            
            # 예시 데이터 (실제로는 processor.stats_dict에서 가져옴)
            example_stats = {
                'received_frames': counter * 10,
                'processed_frames': counter * 9,
                'saved_frames': counter * 8,
                'lost_frames': counter // 10,  # 가끔 손실
                'error_frames': counter // 5,  # 에러 프레임
                'loss_rate': (counter // 10) / max(counter * 10, 1) * 100
            }
            
            print(format_stats_line(timestamp, "stream_1", example_stats))
            
            time.sleep(5)  # 5초마다 업데이트
            
    except KeyboardInterrupt:
        print("\n모니터링 종료")
    except Exception as e:
        print(f"오류: {e}")

if __name__ == "__main__":
    print("📊 RTSP 통계 모니터링 도구")
    print("Ctrl+C로 종료")
    monitor_stats()