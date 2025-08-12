#!/bin/bash

# 6개 RTSP 스트림을 screen으로 백그라운드 실행하는 스크립트
# 사용법: ./start_all_streams.sh

echo "🚀 6개 RTSP 스트림 백그라운드 실행"
echo "================================="

# 설정
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="run.py"
BASE_SESSION_NAME="rtsp_stream"

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
    env_file=".env.stream${i}"
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
    env_file=".env.stream${i}"
    log_file="rtsp_stream${i}.log"
    
    echo ""
    echo "🔄 스트림 ${i} 시작 중..."
    echo "   세션명: $session_name"
    echo "   설정파일: $env_file"
    echo "   로그파일: $log_file"
    
    # .env 파일을 임시로 복사
    cp "$env_file" ".env.temp${i}"
    
    # screen 세션 생성 및 실행
    screen -dmS "$session_name" bash -c "
        cd '$SCRIPT_DIR'
        export DOTENV_PATH='.env.temp${i}'
        echo '스트림 ${i} 시작: $(date)' >> '$log_file'
        echo '설정파일: $env_file' >> '$log_file'
        echo '========================================' >> '$log_file'
        
        # .env 파일을 임시로 .env로 복사하여 실행
        cp '$env_file' '.env'
        python3 '$PYTHON_SCRIPT' 2>&1 | tee -a '$log_file'
        
        echo '스트림 ${i} 종료: $(date)' >> '$log_file'
        rm -f '.env.temp${i}'
        
        # 종료 시 Enter 키 대기 (세션 유지)
        echo '프로세스가 종료되었습니다. Enter 키를 눌러 세션을 종료하세요.'
        read
    "
    
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
screen -dmS "$FILE_MOVER_SESSION" bash -c "
    cd '$SCRIPT_DIR'
    echo '파일 이동 서비스 시작: $(date)' >> file_mover.log
    echo '========================================' >> file_mover.log
    python3 file_mover.py 2>&1 | tee -a file_mover.log
    echo '파일 이동 서비스 종료: $(date)' >> file_mover.log
    
    # 종료 시 Enter 키 대기 (세션 유지)
    echo '파일 이동 서비스가 종료되었습니다. Enter 키를 눌러 세션을 종료하세요.'
    read
"

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
echo "   로그 확인: tail -f rtsp_stream1.log (1~6)"

echo ""
echo "📁 생성된 파일들:"
echo "   로그 파일: rtsp_stream1.log ~ rtsp_stream6.log"
echo "   임시 env: .env.temp1 ~ .env.temp6"

echo ""
echo "⚠️  주의사항:"
echo "   - 각 스트림은 독립적인 프로세스로 실행됩니다"
echo "   - 시스템 리소스 사용량을 모니터링하세요"
echo "   - 로그 파일이 계속 증가하므로 주기적으로 정리하세요" 