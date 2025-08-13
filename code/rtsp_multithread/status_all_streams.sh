#!/bin/bash

# 6개 RTSP 스트림 상태 확인 스크립트
# 사용법: ./status_all_streams.sh

echo "📊 6개 RTSP 스트림 상태 확인"
echo "=========================="

BASE_SESSION_NAME="rtsp_stream"
FILE_MOVER_SESSION="rtsp_file_mover"
BASE_IP="10.2.10.158"
START_PORT=1111

# 스크립트/로그/프로필 경로
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGS_DIR="$SCRIPT_DIR/logs"
# PROFILE 우선순위: env > logs/.current_profile > sim
if [ -z "${PROFILE:-}" ] && [ -f "$LOGS_DIR/.current_profile" ]; then
  PROFILE="$(cat "$LOGS_DIR/.current_profile" 2>/dev/null || echo sim)"
fi
PROFILE="${PROFILE:-sim}"
ENV_BASE_DIR="$SCRIPT_DIR/profiles/$PROFILE"

# 현재 시간
echo "확인 시간: $(date)"
echo ""

# Screen 세션 상태
echo "🖥️  Screen 세션 상태:"
running_streams=$(screen -list | grep "${BASE_SESSION_NAME}" | wc -l)
running_mover=$(screen -list | grep "${FILE_MOVER_SESSION}" | wc -l)
echo "   RTSP 스트림 세션: $running_streams / 6"
echo "   파일 이동 세션: $running_mover / 1"

if [ "$running_streams" -gt 0 ] || [ "$running_mover" -gt 0 ]; then
    screen -list | grep -E "${BASE_SESSION_NAME}|${FILE_MOVER_SESSION}" | sed 's/^/   /'
else
    echo "   ❌ 실행 중인 세션이 없습니다"
fi

echo ""

# 개별 스트림 상태
echo "🎬 개별 스트림 상태:"
for i in {1..6}; do
    session_name="${BASE_SESSION_NAME}${i}"
    port=$((START_PORT + i - 1))
    rtsp_url="rtsp://${BASE_IP}:${port}/live"
    env_file="$ENV_BASE_DIR/.env.stream${i}"
    current_date=$(date +%Y%m%d)
    log_file="$LOGS_DIR/rtsp_stream${i}_${current_date}.log"
    
    echo ""
    echo "   📡 스트림 ${i} (포트 ${port}):"
    echo "      URL: $rtsp_url"
    
    # 세션 상태
    if screen -list | grep -q "$session_name"; then
        echo "      세션: ✅ 실행 중 ($session_name)"
    else
        echo "      세션: ❌ 중지됨"
    fi
    
    # 설정 파일 상태
    if [ -f "$env_file" ]; then
        echo "      설정: ✅ $env_file 존재 (PROFILE=$PROFILE)"
    else
        echo "      설정: ❌ $env_file 없음 (PROFILE=$PROFILE)"
    fi
    
    # 로그 파일 상태
    if [ -f "$log_file" ]; then
        file_size=$(wc -c < "$log_file" 2>/dev/null || echo "0")
        line_count=$(wc -l < "$log_file" 2>/dev/null || echo "0")
        last_modified=$(stat -c %y "$log_file" 2>/dev/null || echo "알 수 없음")
        echo "      로그: ✅ $(basename "$log_file") (${file_size} bytes, ${line_count} lines)"
        echo "            최종 수정: $last_modified"
        
        # 최근 로그 라인 확인 (에러 체크)
        if [ -s "$log_file" ]; then
            last_line=$(tail -n 1 "$log_file" 2>/dev/null || echo "")
            if echo "$last_line" | grep -i "error\|fail\|exception" > /dev/null; then
                echo "      ⚠️  최근 에러 감지: $last_line"
            fi
        fi
    else
        echo "      로그: ❌ $(basename "$log_file") 없음 (LOGS_DIR=$LOGS_DIR)"
    fi
done

echo ""

# 시스템 리소스 상태
echo "🖥️  시스템 리소스:"

# Python 프로세스 확인
python_processes=$(pgrep -f "python.*run.py" | wc -l)
echo "   Python 프로세스: $python_processes 개"

# CPU 사용률
if command -v top &> /dev/null; then
    cpu_usage=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | sed 's/%us,//')
    echo "   CPU 사용률: ${cpu_usage}%"
fi

# 메모리 사용률
if command -v free &> /dev/null; then
    memory_info=$(free | grep Mem | awk '{printf "%.1f%%", $3/$2 * 100}')
    echo "   메모리 사용률: $memory_info"
fi

# 디스크 사용률 (로그/출력 디렉토리)
if command -v du &> /dev/null; then
    if [ -d "$LOGS_DIR" ]; then
        logs_size=$(du -sh "$LOGS_DIR" 2>/dev/null | awk '{print $1}')
        echo "   로그 폴더 용량($LOGS_DIR): $logs_size"
    fi
fi

echo ""

# 출력 디렉토리 상태
echo "📁 출력 디렉토리 상태:"
output_dir="./output"
if [ -d "$output_dir" ]; then
    video_count=$(find "$output_dir" -name "*.mp4" | wc -l)
    temp_count=$(find "$output_dir" -name "temp_*.mp4" | wc -l)
    total_size=$(du -sh "$output_dir" 2>/dev/null | awk '{print $1}')
    
    echo "   디렉토리: ✅ $output_dir"
    echo "   완료된 영상: $video_count 개"
    echo "   진행 중 영상: $temp_count 개"
    echo "   총 용량: $total_size"
    
    # 최근 생성된 파일
    if [ "$video_count" -gt 0 ]; then
        echo "   최근 파일:"
        find "$output_dir" -name "*.mp4" -not -name "temp_*" -printf "      %TY-%Tm-%Td %TH:%TM %f\n" | sort -r | head -3
    fi
else
    echo "   디렉토리: ❌ $output_dir 없음"
fi

echo ""

# 빠른 액션 가이드
echo "🔧 빠른 액션:"
echo "   전체 시작: ./start_all_streams.sh"
echo "   전체 중지: ./stop_all_streams.sh"
echo "   특정 세션 접속: screen -r rtsp_stream1 (1~6)"
echo "   실시간 로그: tail -f \"$LOGS_DIR/rtsp_stream1_$(date +%Y%m%d).log\" (1~6)"

# 파일 이동 서비스 제어
if [ "$running_mover" -gt 0 ]; then
    echo ""
    echo "📦 파일 이동 서비스 제어:"
    echo "   접속: screen -r $FILE_MOVER_SESSION"
    echo "   로그: tail -f \"$LOGS_DIR/file_mover_$(date +%Y%m%d).log\""
fi 