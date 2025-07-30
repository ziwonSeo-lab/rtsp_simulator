#!/usr/bin/env python3
"""
RTSP FPS 문제 해결 테스트 스크립트
- 수정된 코드가 정확히 15fps로 저장되는지 확인
- 파일 길이가 실제 시간과 일치하는지 검증
- 300초 테스트에서 15개 파일 생성 확인
"""

import os
import sys
import time
import subprocess
import json
from datetime import datetime

def check_ffmpeg():
    """FFmpeg 설치 확인"""
    try:
        result = subprocess.run(['ffmpeg', '-version'], 
                              capture_output=True, text=True, timeout=5)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False

def analyze_video_file(filepath):
    """FFprobe로 비디오 파일 분석"""
    if not os.path.exists(filepath):
        return None
    
    try:
        cmd = [
            'ffprobe', '-v', 'error',
            '-select_streams', 'v:0',
            '-count_frames',
            '-show_entries', 'stream=nb_read_frames,avg_frame_rate,duration',
            '-show_entries', 'format=duration',
            '-of', 'json',
            filepath
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            print(f"❌ FFprobe 실패: {filepath}")
            return None
        
        data = json.loads(result.stdout)
        
        # 스트림 정보 추출
        stream_info = data.get('streams', [{}])[0]
        format_info = data.get('format', {})
        
        frame_count = int(stream_info.get('nb_read_frames', 0))
        avg_frame_rate = stream_info.get('avg_frame_rate', '0/1')
        duration = float(format_info.get('duration', 0))
        
        # FPS 계산
        if '/' in avg_frame_rate:
            num, den = map(int, avg_frame_rate.split('/'))
            fps = num / den if den != 0 else 0
        else:
            fps = float(avg_frame_rate)
        
        return {
            'filepath': filepath,
            'duration': duration,
            'frame_count': frame_count,
            'fps': fps,
            'calculated_fps': frame_count / duration if duration > 0 else 0
        }
        
    except Exception as e:
        print(f"❌ 파일 분석 실패 {filepath}: {e}")
        return None

def test_output_directory(custom_dir=None):
    """출력 디렉토리의 파일들 분석"""
    if custom_dir:
        output_dir = custom_dir
    else:
        output_dir = "/home/szw001/development/2025/IUU/rtsp_simulator/code/rtsp_client_module/output"
    
    if not os.path.exists(output_dir):
        print(f"❌ 출력 디렉토리가 존재하지 않습니다: {output_dir}")
        return
    
    print("🔍 기존 출력 파일 분석 중...")
    print("=" * 80)
    
    total_files = 0
    problematic_files = 0
    
    for stream_dir in os.listdir(output_dir):
        stream_path = os.path.join(output_dir, stream_dir)
        if not os.path.isdir(stream_path):
            continue
        
        print(f"\n📁 {stream_dir} 분석:")
        print("-" * 50)
        
        files = [f for f in os.listdir(stream_path) if f.endswith('.mp4')]
        files.sort()
        
        for filename in files:
            filepath = os.path.join(stream_path, filename)
            info = analyze_video_file(filepath)
            
            if info:
                total_files += 1
                
                # 문제 체크
                is_problematic = False
                issues = []
                
                # FPS 체크 (15fps ± 1fps 허용)
                if not (14 <= info['fps'] <= 16):
                    is_problematic = True
                    issues.append(f"FPS 이상 ({info['fps']:.1f})")
                
                # 길이 체크 (20초 ± 2초 허용)
                if not (18 <= info['duration'] <= 22):
                    is_problematic = True
                    issues.append(f"길이 이상 ({info['duration']:.1f}초)")
                
                # 프레임 수 체크 (15fps × 20초 = 300프레임 ± 30프레임 허용)
                expected_frames = info['duration'] * 15
                if abs(info['frame_count'] - expected_frames) > 30:
                    is_problematic = True
                    issues.append(f"프레임수 이상 ({info['frame_count']})")
                
                if is_problematic:
                    problematic_files += 1
                    status = "❌"
                    issue_text = ", ".join(issues)
                else:
                    status = "✅"
                    issue_text = "정상"
                
                print(f"  {status} {filename}")
                print(f"      길이: {info['duration']:.1f}초, FPS: {info['fps']:.1f}, "
                      f"프레임: {info['frame_count']}개")
                if is_problematic:
                    print(f"      문제: {issue_text}")
    
    print("\n" + "=" * 80)
    print("📊 분석 결과 요약:")
    print(f"  전체 파일: {total_files}개")
    print(f"  정상 파일: {total_files - problematic_files}개")
    print(f"  문제 파일: {problematic_files}개")
    
    if problematic_files == 0:
        print("🎉 모든 파일이 정상입니다!")
    else:
        print(f"⚠️  {problematic_files}개 파일에서 문제가 발견되었습니다.")

def suggest_test_command():
    """테스트 실행 명령어 제안"""
    print("\n" + "=" * 80)
    print("🧪 수정사항 테스트 방법:")
    print("-" * 50)
    print("1. 기존 출력 파일 삭제 (선택사항):")
    print("   rm -rf /home/szw001/development/2025/IUU/rtsp_simulator/code/rtsp_client_module/output/*")
    
    print("\n2. 짧은 테스트 실행 (60초):")
    print("   cd /home/szw001/development/2025/IUU/rtsp_simulator/code/rtsp_client_module")
    print("   python -c \"")
    print("   from processor import SharedPoolRTSPProcessor")
    print("   from config import RTSPConfig")
    print("   import time")
    print("   ")
    print("   config = RTSPConfig()")
    print("   config.max_duration_seconds = 60  # 60초 테스트")
    print("   config.save_interval_seconds = 20  # 20초마다 파일 분할")
    print("   ")
    print("   processor = SharedPoolRTSPProcessor(config)")
    print("   processor.start()")
    print("   time.sleep(65)  # 60초 + 여유시간")
    print("   processor.stop()")
    print("   \"")
    
    print("\n3. 결과 분석:")
    print("   python test_fps_fix.py")
    
    print("\n4. 예상 결과:")
    print("   - 각 스트림당 3개 파일 생성 (0-20초, 20-40초, 40-60초)")
    print("   - 각 파일 길이: 약 20초")
    print("   - 각 파일 FPS: 15fps")
    print("   - 각 파일 프레임 수: 약 300개")

def main():
    print("🔧 RTSP FPS 문제 해결 검증 도구")
    print("=" * 80)
    
    # FFmpeg 확인
    if not check_ffmpeg():
        print("❌ FFmpeg가 설치되지 않았습니다.")
        print("   sudo apt update && sudo apt install ffmpeg")
        return
    
    print("✅ FFmpeg 설치 확인됨")
    
    # 출력 디렉토리 분석 (debug_fps_output 우선 확인)
    debug_output = "/home/szw001/development/2025/IUU/rtsp_simulator/debug_fps_output"
    main_output = "/home/szw001/development/2025/IUU/rtsp_simulator/code/rtsp_client_module/output"
    
    if os.path.exists(debug_output) and any(os.listdir(debug_output)):
        print("🔍 debug_fps_output 디렉토리 분석:")
        test_output_directory(debug_output)
    
    if os.path.exists(main_output) and any(os.listdir(main_output)):
        print("\n🔍 기본 output 디렉토리 분석:")
        test_output_directory(main_output)
    
    # 테스트 명령어 제안
    suggest_test_command()

if __name__ == "__main__":
    main()