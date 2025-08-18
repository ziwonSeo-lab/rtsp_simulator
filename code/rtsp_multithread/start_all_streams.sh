#!/bin/bash

# 6개 RTSP 스트림을 screen으로 백그라운드 실행하는 스크립트
# 사용법: ./start_all_streams.sh

echo "🚀 6개 RTSP 스트림 백그라운드 실행"
echo "================================="

# 설정
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="run.py"
BASE_SESSION_NAME="rtsp_stream"
# 프로필 기반 설정 (sim/camera 등)
PROFILE="${PROFILE:-sim}"
ENV_BASE_DIR="$SCRIPT_DIR/profiles/$PROFILE"
# 로그 디렉터리 우선순위: LOG_DIR > FINAL_OUTPUT_PATH/logs > SCRIPT_DIR/logs
if [ -n "$LOG_DIR" ]; then
    LOGS_DIR="$LOG_DIR"
elif [ -n "$FINAL_OUTPUT_PATH" ]; then
    LOGS_DIR="$FINAL_OUTPUT_PATH/logs"
else
    LOGS_DIR="$SCRIPT_DIR/logs"
fi
mkdir -p "$LOGS_DIR"
# 현재 PROFILE 기록 (상태 스크립트가 자동 추적할 수 있도록)
echo -n "$PROFILE" > "$LOGS_DIR/.current_profile"

# 사전 확인
echo "📋 사전 확인 중..."

# Python 스크립트 존재 확인
if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo "❌ $PYTHON_SCRIPT 파일을 찾을 수 없습니다"
    exit 1
fi

# screen 설치 확인
if ! command -v screen &> /dev/null; then
    echo "❌ screen이 설치되지 않았습니다"
    echo "   설치: sudo apt-get install screen"
    exit 1
fi

# .env 파일들 존재 확인
missing_env=false
for i in {1..6}; do
    env_file="$ENV_BASE_DIR/.env.stream${i}"
    if [ ! -f "$env_file" ]; then
        echo "❌ $env_file 파일이 없습니다"
        missing_env=true
    fi
done

if [ "$missing_env" = true ]; then
    echo ""
    echo "💡 .env 파일을 먼저 생성하세요:"
    echo "   ./generate_env.sh"
    exit 1
fi

# 가상환경 활성화 (env-blur) [[memory:3627098]]
if [ -f "$HOME/env-blur/bin/activate" ]; then
    echo "🐍 가상환경 활성화: env-blur"
    source "$HOME/env-blur/bin/activate"
else
    echo "⚠️  env-blur 가상환경을 찾을 수 없습니다"
    echo "   계속 진행하지만 패키지 오류가 발생할 수 있습니다"
fi

echo ""
echo "🎬 6개 스트림 실행 시작..."

# 기존 세션 종료 (선택사항)
echo "🧹 기존 세션 정리 중..."
for i in {1..6}; do
    session_name="${BASE_SESSION_NAME}${i}"
    if screen -list | grep -q "$session_name"; then
        screen -S "$session_name" -X quit 2>/dev/null
        echo "   종료: $session_name"
    fi
done

sleep 2

# 6개 스트림 실행
for i in {1..6}; do
    session_name="${BASE_SESSION_NAME}${i}"
    env_file="$ENV_BASE_DIR/.env.stream${i}"
    log_file="rtsp_stream${i}_$(date +%Y%m%d).log"
    
    echo ""
    echo "🔄 스트림 ${i} 시작 중..."
    echo "   세션명: $session_name"
    echo "   설정파일: $env_file"
    echo "   로그파일: $log_file"
    
            # .env 파일을 임시로 복사
        cp "$env_file" ".env.temp${i}"
        # 런타임에 사용할 값들을 자식 셸로 전달
        export STREAM_INDEX="$i"
        export ENV_FILE="$env_file"
        export PY_SCRIPT="$PYTHON_SCRIPT"
        export SCRIPT_DIR="$SCRIPT_DIR"
        # 미리 날짜 포함 로그 파일명을 계산하여 전달
        export STREAM_LOG_FILE="rtsp_stream${i}_$(date +%Y%m%d).log"
        
        # screen 세션 생성 및 실행
        # 임시 실행 스크립트 생성
            temp_script="$SCRIPT_DIR/.tmp_run_stream_${i}.sh"
    cat > "$temp_script" <<'EOF'
#!/bin/bash
cd "$SCRIPT_DIR"
SELF_SCRIPT="$(realpath "${BASH_SOURCE[0]}" 2>/dev/null || echo "$0")"
trap 'rm -f "$SELF_SCRIPT"' EXIT
rm -f "$SELF_SCRIPT"
export DOTENV_PATH=".env.temp${STREAM_INDEX}"
# 로그 디렉터리 설정 (.env에서 LOG_DIR 우선, 없으면 FINAL_OUTPUT_PATH/logs)
env_log_dir=""
env_final_output=""
if [ -n "$ENV_FILE" ] && [ -f "$ENV_FILE" ]; then
    env_log_dir=$(grep -E '^LOG_DIR=' "$ENV_FILE" | tail -n1 | cut -d= -f2-)
    env_final_output=$(grep -E '^FINAL_OUTPUT_PATH=' "$ENV_FILE" | tail -n1 | cut -d= -f2-)
fi
if [ -n "$env_log_dir" ]; then
    LOG_DIR="$env_log_dir"
elif [ -n "$env_final_output" ]; then
    LOG_DIR="$env_final_output/logs"
else
    LOG_DIR="$SCRIPT_DIR/logs"
fi
mkdir -p "$LOG_DIR"
# 날짜별 로그 파일 설정 및 헤더 기록
current_date=$(date +%Y%m%d)
date_dir=$(date +%Y/%m/%d)
mkdir -p "$LOG_DIR/$date_dir"
log_file="$LOG_DIR/$date_dir/rtsp_stream${STREAM_INDEX}_${current_date}.log"
echo "스트림 ${STREAM_INDEX} 시작: $(date)" >> "$log_file"
echo "설정파일: $ENV_FILE" >> "$log_file"
echo "========================================" >> "$log_file"

# .env 파일을 임시로 .env로 복사하여 실행
cp "$ENV_FILE" ".env"
# 날짜 변경 시 자동 회전하며 로그 기록 (LOG_DIR은 셸 내부에서만 사용)
python3 -u "$PY_SCRIPT" 2>&1 | while IFS= read -r line; do
    new_date=$(date +%Y%m%d)
    if [ "$new_date" != "$current_date" ]; then
        current_date="$new_date"
        date_dir=$(date +%Y/%m/%d)
        mkdir -p "$LOG_DIR/$date_dir"
        log_file="$LOG_DIR/$date_dir/rtsp_stream${STREAM_INDEX}_${current_date}.log"
        echo "----- 날짜 변경: $(date) -----" | tee -a "$log_file"
    fi
    echo "$line" | tee -a "$log_file"
done

echo "스트림 ${i} 종료: $(date)" >> "$log_file"
rm -f ".env.temp${i}"

# 종료 시 Enter 키 대기 (세션 유지)
echo "프로세스가 종료되었습니다. Enter 키를 눌러 세션을 종료하세요."
read
EOF

    chmod +x "$temp_script"

    # screen 세션 생성 및 실행
    screen -dmS "$session_name" bash "$temp_script"
    
    # 세션 시작 확인
    sleep 1
    if screen -list | grep -q "$session_name"; then
        echo "   ✅ $session_name 세션 시작됨"
    else
        echo "   ❌ $session_name 세션 시작 실패"
    fi
done

echo ""
echo "🚀 파일 이동 서비스 시작 중..."

# 파일 이동 서비스 세션 시작
FILE_MOVER_SESSION="rtsp_file_mover"
if screen -list | grep -q "$FILE_MOVER_SESSION"; then
    echo "   기존 파일 이동 세션 종료..."
    screen -S "$FILE_MOVER_SESSION" -X quit 2>/dev/null
    sleep 1
fi

    # 파일 이동 서비스를 별도 세션에서 실행
    # 임시 실행 스크립트 생성
    temp_mover_script="$SCRIPT_DIR/.tmp_run_file_mover.sh"
    # 파일 이동 서비스가 참조할 env 파일(최종 경로 추출용)
    FM_ENV_REF="$ENV_BASE_DIR/.env.stream1"
    cat > "$temp_mover_script" <<'EOF'
#!/bin/bash
cd "$SCRIPT_DIR"
SELF_SCRIPT="$(realpath "${BASH_SOURCE[0]}" 2>/dev/null || echo "$0")"
trap 'rm -f "$SELF_SCRIPT"' EXIT
rm -f "$SELF_SCRIPT"
# 로그 디렉터리 설정 (.env에서 LOG_DIR 우선, 없으면 FINAL_OUTPUT_PATH/logs)
env_log_dir=""
env_final_output=""
if [ -n "$FM_ENV_REF" ] && [ -f "$FM_ENV_REF" ]; then
    env_log_dir=$(grep -E '^LOG_DIR=' "$FM_ENV_REF" | tail -n1 | cut -d= -f2-)
    env_final_output=$(grep -E '^FINAL_OUTPUT_PATH=' "$FM_ENV_REF" | tail -n1 | cut -d= -f2-)
fi
if [ -n "$env_log_dir" ]; then
    LOG_DIR="$env_log_dir"
elif [ -n "$env_final_output" ]; then
    LOG_DIR="$env_final_output/logs"
else
    LOG_DIR="$SCRIPT_DIR/logs"
fi
mkdir -p "$LOG_DIR"
# 날짜별 로그 파일 설정 및 헤더 기록
current_date=$(date +%Y%m%d)
date_dir=$(date +%Y/%m/%d)
mkdir -p "$LOG_DIR/$date_dir"
log_prefix="file_mover_"
log_file="$LOG_DIR/$date_dir/${log_prefix}${current_date}.log"
echo "파일 이동 서비스 시작: $(date)" >> "$log_file"
echo "========================================" >> "$log_file"
# 날짜 변경 시 자동 회전하며 로그 기록 (LOG_DIR은 셸 내부에서만 사용)
python3 -u file_mover.py 2>&1 | while IFS= read -r line; do
    new_date=$(date +%Y%m%d)
    if [ "$new_date" != "$current_date" ]; then
        current_date="$new_date"
        date_dir=$(date +%Y/%m/%d)
        mkdir -p "$LOG_DIR/$date_dir"
        log_file="$LOG_DIR/$date_dir/${log_prefix}${current_date}.log"
        echo "----- 날짜 변경: $(date) -----" | tee -a "$log_file"
    fi
    echo "$line" | tee -a "$log_file"
done
echo "파일 이동 서비스 종료: $(date)" >> "$log_file"

# 종료 시 Enter 키 대기 (세션 유지)
echo "파일 이동 서비스가 종료되었습니다. Enter 키를 눌러 세션을 종료하세요."
read
EOF

    chmod +x "$temp_mover_script"

    # screen 세션 생성 및 실행
    screen -dmS "$FILE_MOVER_SESSION" bash "$temp_mover_script"

# 파일 이동 서비스 시작 확인
sleep 1
if screen -list | grep -q "$FILE_MOVER_SESSION"; then
    echo "   ✅ 파일 이동 서비스 시작됨 ($FILE_MOVER_SESSION)"
else
    echo "   ⚠️  파일 이동 서비스 시작 실패"
fi

echo ""
echo "✅ 6개 스트림 + 파일 이동 서비스 실행 완료!"
echo ""
echo "📊 실행 중인 세션 목록:"
screen -list | grep -E "${BASE_SESSION_NAME}|${FILE_MOVER_SESSION}" | sed 's/^/   /'

echo ""
echo "🔧 관리 명령어:"
echo "   전체 상태 확인: screen -list"
echo "   개별 세션 접속: screen -r ${BASE_SESSION_NAME}1 (1~6)"
echo "   세션에서 나가기: Ctrl+A, D"
echo "   전체 중지: ./stop_all_streams.sh"
echo "   로그 확인: tail -f \"$LOGS_DIR/rtsp_stream1_$(date +%Y%m%d).log\" (1~6)"

echo ""
echo "📁 생성된 파일들:"
echo "   로그 파일 폴더: $LOGS_DIR"
echo "   스트림 로그: rtsp_stream1_$(date +%Y%m%d).log ~ rtsp_stream6_$(date +%Y%m%d).log"
echo "   임시 env: .env.temp1 ~ .env.temp6"

echo ""
echo "⚠️  주의사항:"
echo "   - 각 스트림은 독립적인 프로세스로 실행됩니다"
echo "   - 시스템 리소스 사용량을 모니터링하세요"
echo "   - 로그 파일이 계속 증가하므로 주기적으로 정리하세요" 