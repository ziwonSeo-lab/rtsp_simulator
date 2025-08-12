#!/bin/bash

# 6개 RTSP 스트림용 .env 파일 자동 생성 스크립트
# 사용법: ./generate_env.sh
# RTSP URL: rtsp://10.2.10.158:1111-1116/live (스트림 1-6)

echo "📝 6개 RTSP 스트림용 .env 파일 자동 생성"
echo "========================================"

# 기본 설정
BASE_IP="10.2.10.158"
START_PORT=1111
END_PORT=1116
VESSEL_NAME=${VESSEL_NAME:-vesselTest}

# 비트레이트 설정
TARGET_BITRATE=${TARGET_BITRATE:-5M}
MIN_BITRATE=${MIN_BITRATE:-1M}
MAX_BITRATE=${MAX_BITRATE:-10M}

# 블러 모듈 설정
export BLUR_MODULE_PATH=${BLUR_MODULE_PATH:-/home/koast-user/rtsp_simulator/blur_module/ipcamera_blur.py}
export BLUR_ENABLED=${BLUR_ENABLED:-true}
export BLUR_CONFIDENCE=${BLUR_CONFIDENCE:-0.5}

# 출력 설정
export TEMP_OUTPUT_PATH=${TEMP_OUTPUT_PATH:-./output/temp/}
export FINAL_OUTPUT_PATH=${FINAL_OUTPUT_PATH:-/mnt/raid5}
export DEFAULT_INPUT_FPS=${DEFAULT_INPUT_FPS:-15.0}
export VIDEO_SEGMENT_DURATION=${VIDEO_SEGMENT_DURATION:-20} # 영상 길이 설정
export VIDEO_WIDTH=${VIDEO_WIDTH:-1920}
export VIDEO_HEIGHT=${VIDEO_HEIGHT:-1080}
export DEFAULT_LATITUDE=${DEFAULT_LATITUDE:-37.5665}
export DEFAULT_LONGITUDE=${DEFAULT_LONGITUDE:-126.9780}
export FRAME_QUEUE_SIZE=${FRAME_QUEUE_SIZE:-100}
export CONNECTION_TIMEOUT=${CONNECTION_TIMEOUT:-10}
export RECONNECT_INTERVAL=${RECONNECT_INTERVAL:-5}
export ENABLE_MONITORING=${ENABLE_MONITORING:-true}
export MONITORING_INTERVAL=${MONITORING_INTERVAL:-1.0}

# 6개 스트림용 .env 파일 생성
for i in {1..6}; do
    PORT=$((START_PORT + i - 1))
    RTSP_URL="rtsp://${BASE_IP}:${PORT}/live"
    VESSEL_NAME="$VESSEL_NAME"
    STREAM_NUMBER=$i
    ENV_FILE=".env.stream${i}"
    
    echo ""
    echo "🔄 스트림 ${i} .env 파일 생성 중..."
    echo "   URL: $RTSP_URL"
    echo "   선박명: $VESSEL_NAME"
    echo "   파일: $ENV_FILE"
    

    
    # .env 파일 생성
    cat > "$ENV_FILE" << EOF
# RTSP Multithread Processor 환경변수 설정 - 스트림 ${i}
# 자동 생성: $(date)
# 생성 스크립트: generate_env.sh
# RTSP URL: $RTSP_URL

# =============================================================================
# 필수 설정 - 스트림 ${i}
# =============================================================================
RTSP_URL=$RTSP_URL
VESSEL_NAME=$VESSEL_NAME
STREAM_NUMBER=$STREAM_NUMBER

# =============================================================================
# 블러 처리 설정
# =============================================================================
BLUR_MODULE_PATH=$BLUR_MODULE_PATH
BLUR_ENABLED=$BLUR_ENABLED
BLUR_CONFIDENCE=$BLUR_CONFIDENCE

# =============================================================================
# 출력 설정
# =============================================================================
TEMP_OUTPUT_PATH=$TEMP_OUTPUT_PATH
FINAL_OUTPUT_PATH=$FINAL_OUTPUT_PATH
DEFAULT_INPUT_FPS=$DEFAULT_INPUT_FPS
VIDEO_SEGMENT_DURATION=$VIDEO_SEGMENT_DURATION

# 영상 해상도 설정
VIDEO_WIDTH=$VIDEO_WIDTH
VIDEO_HEIGHT=$VIDEO_HEIGHT

# =============================================================================
# GPS 좌표 설정
# =============================================================================
DEFAULT_LATITUDE=$DEFAULT_LATITUDE
DEFAULT_LONGITUDE=$DEFAULT_LONGITUDE

# =============================================================================
# 성능 설정
# =============================================================================
FRAME_QUEUE_SIZE=$FRAME_QUEUE_SIZE
CONNECTION_TIMEOUT=$CONNECTION_TIMEOUT
RECONNECT_INTERVAL=$RECONNECT_INTERVAL

# =============================================================================
# 모니터링 설정
# =============================================================================
ENABLE_MONITORING=$ENABLE_MONITORING
MONITORING_INTERVAL=$MONITORING_INTERVAL

# =============================================================================
# 고급 설정 (필요시 주석 해제하여 사용)
# =============================================================================
# LOG_LEVEL=INFO
# LOG_FILE=rtsp_processor_stream${i}.log
# DEFAULT_MAX_DURATION=3600

# FFmpeg 고급 설정
# FFMPEG_PRESET=medium
# FFMPEG_TUNE=film
FFMPEG_TARGET_BITRATE=$TARGET_BITRATE
FFMPEG_MIN_BITRATE=$MIN_BITRATE
FFMPEG_MAX_BITRATE=$MAX_BITRATE
EOF

    echo "   ✅ $ENV_FILE 생성 완료"
done

# 출력 디렉토리 생성
if [ ! -d "$DEFAULT_OUTPUT_PATH" ]; then
    mkdir -p "$DEFAULT_OUTPUT_PATH"
    echo "📁 출력 디렉토리 생성: $DEFAULT_OUTPUT_PATH"
fi

echo ""
echo "✅ 6개 스트림용 .env 파일 생성 완료!"
echo ""
echo "📄 생성된 파일들:"
for i in {1..6}; do
    PORT=$((START_PORT + i - 1))
    ENV_FILE=".env.stream${i}"
    FILE_SIZE=$(wc -c < "$ENV_FILE")
    echo "   $ENV_FILE (${FILE_SIZE} bytes) - rtsp://${BASE_IP}:${PORT}/live"
done

# 블러 모듈 확인
echo ""
if [ -f "$BLUR_MODULE_PATH" ]; then
    echo "블러 모듈: ✅ 존재 ($BLUR_MODULE_PATH)"
else
    echo "블러 모듈: ⚠️  없음 - 기본 블러 사용 ($BLUR_MODULE_PATH)"
fi

echo ""
echo "📋 현재 설정:"
echo "   선박명: vesselTest"
echo "   비디오 저장 간격: ${VIDEO_SEGMENT_DURATION}초"
echo "   해상도: ${VIDEO_WIDTH}x${VIDEO_HEIGHT}"
echo "   타겟 비트레이트: $TARGET_BITRATE"
echo "   최소 비트레이트: $MIN_BITRATE"
echo "   최대 비트레이트: $MAX_BITRATE"

echo ""
echo "💡 비트레이트 변경 방법:"
echo "   환경변수 설정: TARGET_BITRATE=8M MIN_BITRATE=2M MAX_BITRATE=15M ./generate_env.sh"
echo "   또는 스크립트 상단의 비트레이트 설정 부분 직접 수정"

echo ""
echo "🚀 실행 준비 완료!"
echo "   개별 실행: python3 run.py (해당 .env.streamX 파일을 .env로 복사 후)"
echo "   전체 실행: ./start_all_streams.sh" 