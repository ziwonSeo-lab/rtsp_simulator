#!/bin/bash

# Jetson Orin 전용 6개 RTSP 스트림용 .env 파일 자동 생성 스크립트
# 사용법: ./generate_env_jetson.sh
# RTSP URL: rtsp://10.2.10.158:1111-1116/live (스트림 1-6)

echo "📝 Jetson Orin용 6개 RTSP 스트림 .env 파일 자동 생성"
echo "=============================================="

# 기본 설정
BASE_IP="${BASE_IP:-10.2.10.158}"
START_PORT=${START_PORT:-1111}
END_PORT=${END_PORT:-1116}
VESSEL_NAME=${VESSEL_NAME:-vesselTest}

# 비트레이트 설정 (Jetson 권장 기본값)
TARGET_BITRATE=${TARGET_BITRATE:-5M}
MIN_BITRATE=${MIN_BITRATE:-1M}
MAX_BITRATE=${MAX_BITRATE:-10M}

# 블러 모듈 설정 (Jetson: koast 사용자 경로)
export BLUR_MODULE_PATH=${BLUR_MODULE_PATH:-/home/koast/rtsp_simulator/blur_module/ipcamera_blur.py}
export BLUR_ENABLED=${BLUR_ENABLED:-true}
export BLUR_CONFIDENCE=${BLUR_CONFIDENCE:-0.5}

# 출력/영상 설정
export TEMP_OUTPUT_PATH=${TEMP_OUTPUT_PATH:-./output/temp/}
export FINAL_OUTPUT_PATH=${FINAL_OUTPUT_PATH:-/mnt/nas}
export DEFAULT_INPUT_FPS=${DEFAULT_INPUT_FPS:-15.0}
export VIDEO_SEGMENT_DURATION=${VIDEO_SEGMENT_DURATION:-20}
export VIDEO_WIDTH=${VIDEO_WIDTH:-1920}
export VIDEO_HEIGHT=${VIDEO_HEIGHT:-1080}
export DEFAULT_LATITUDE=${DEFAULT_LATITUDE:-37.5665}
export DEFAULT_LONGITUDE=${DEFAULT_LONGITUDE:-126.9780}
export FRAME_QUEUE_SIZE=${FRAME_QUEUE_SIZE:-100}
export CONNECTION_TIMEOUT=${CONNECTION_TIMEOUT:-10}
export RECONNECT_INTERVAL=${RECONNECT_INTERVAL:-5}
export ENABLE_MONITORING=${ENABLE_MONITORING:-true}
export MONITORING_INTERVAL=${MONITORING_INTERVAL:-1.0}

# API 설정
export BLACKBOX_API_URL=${BLACKBOX_API_URL:-http://localhost}
export API_TIMEOUT=${API_TIMEOUT:-5}
export API_POLL_INTERVAL=${API_POLL_INTERVAL:-1.0}
export BLACKBOX_ENABLED=${BLACKBOX_ENABLED:-false}

# 녹화 조건 설정
export RECORDING_SPEED_THRESHOLD=${RECORDING_SPEED_THRESHOLD:-5.0}

# FFmpeg Jetson 최적화 (rawvideo -> 하드웨어 인코딩 권장)
# 기본: v4l2m2m (폭넓은 호환). NVENC 가능 시 아래 대안 주석 해제
export FFMPEG_VIDEO_CODEC=${FFMPEG_VIDEO_CODEC:-h264_v4l2m2m}
# 대안: NVENC 사용 (지원되는 ffmpeg 빌드에서만 동작)
# export FFMPEG_VIDEO_CODEC=h264_nvenc
export FFMPEG_INPUT_FPS=${FFMPEG_INPUT_FPS:-15}
export FFMPEG_OUTPUT_FPS=${FFMPEG_OUTPUT_FPS:-15}
export FFMPEG_PRESET=${FFMPEG_PRESET:-fast}
export FFMPEG_TUNE=${FFMPEG_TUNE:-film}
export FFMPEG_VSYNC=${FFMPEG_VSYNC:-drop}
export FFMPEG_LOGLEVEL=${FFMPEG_LOGLEVEL:-error}
# 비트레이트는 위 상단 값 재사용
export FFMPEG_TARGET_BITRATE=$TARGET_BITRATE
export FFMPEG_MIN_BITRATE=$MIN_BITRATE
export FFMPEG_MAX_BITRATE=$MAX_BITRATE

# 6개 스트림용 .env 파일 생성
for i in {1..6}; do
    PORT=$((START_PORT + i - 1))
    RTSP_URL="rtsp://${BASE_IP}:${PORT}/live"
    VESSEL_NAME_VALUE="$VESSEL_NAME"
    STREAM_NUMBER=$i
    ENV_FILE=".env.stream${i}"

    echo ""
    echo "🔄 스트림 ${i} .env 파일 생성 중..."
    echo "   URL: $RTSP_URL"
    echo "   선박명: $VESSEL_NAME_VALUE"
    echo "   파일: $ENV_FILE"

    # .env 파일 생성
    cat > "$ENV_FILE" << EOF
# RTSP Multithread Processor 환경변수 설정 - Jetson 스트림 ${i}
# 자동 생성: $(date)
# 생성 스크립트: generate_env_jetson.sh
# RTSP URL: $RTSP_URL

# =============================================================================
# 필수 설정 - 스트림 ${i}
# =============================================================================
RTSP_URL=$RTSP_URL
VESSEL_NAME=$VESSEL_NAME_VALUE
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
# API 설정
# =============================================================================
BLACKBOX_ENABLED=$BLACKBOX_ENABLED
BLACKBOX_API_URL=$BLACKBOX_API_URL
API_TIMEOUT=$API_TIMEOUT
API_POLL_INTERVAL=$API_POLL_INTERVAL

# =============================================================================
# 녹화 조건 설정
# =============================================================================
RECORDING_SPEED_THRESHOLD=$RECORDING_SPEED_THRESHOLD

# =============================================================================
# FFmpeg 인코딩 설정 (Jetson)
# =============================================================================
FFMPEG_VIDEO_CODEC=$FFMPEG_VIDEO_CODEC
FFMPEG_INPUT_FPS=$FFMPEG_INPUT_FPS
FFMPEG_OUTPUT_FPS=$FFMPEG_OUTPUT_FPS
FFMPEG_PRESET=$FFMPEG_PRESET
FFMPEG_TUNE=$FFMPEG_TUNE
FFMPEG_VSYNC=$FFMPEG_VSYNC
FFMPEG_LOGLEVEL=$FFMPEG_LOGLEVEL
FFMPEG_TARGET_BITRATE=$TARGET_BITRATE
FFMPEG_MIN_BITRATE=$MIN_BITRATE
FFMPEG_MAX_BITRATE=$MAX_BITRATE

# =============================================================================
# 고급 설정 (필요시 주석 해제하여 사용)
# =============================================================================
# LOG_LEVEL=DEBUG
# LOG_FILE=rtsp_processor_stream${i}.log
LOG_ROTATION=on
LOG_ROTATE_INTERVAL=1
LOG_BACKUP_COUNT=7
# DEFAULT_MAX_DURATION=3600
# 하드웨어 가속 강제 (필요시): FFMPEG_HWACCEL=nvidia
EOF

    echo "   ✅ $ENV_FILE 생성 완료"

done

# 출력 디렉토리 생성
if [ ! -d "$TEMP_OUTPUT_PATH" ]; then
    mkdir -p "$TEMP_OUTPUT_PATH"
    echo "📁 출력 디렉토리 생성: $TEMP_OUTPUT_PATH"
fi

# 블러 모듈 확인
echo ""
if [ -f "$BLUR_MODULE_PATH" ]; then
    echo "블러 모듈: ✅ 존재 ($BLUR_MODULE_PATH)"
else
    echo "블러 모듈: ⚠️  없음 - 기본 블러 사용 ($BLUR_MODULE_PATH)"
fi

# 요약 출력
echo ""
echo "✅ Jetson .env 파일 생성 완료!"
echo "📄 생성된 파일들:"
for i in {1..6}; do
    PORT=$((START_PORT + i - 1))
    ENV_FILE=".env.stream${i}"
    FILE_SIZE=$(wc -c < "$ENV_FILE")
    echo "   $ENV_FILE (${FILE_SIZE} bytes) - rtsp://${BASE_IP}:${PORT}/live"
done

echo ""
echo "📋 현재 설정(요약):"
echo "   선박명: $VESSEL_NAME"
echo "   비디오 저장 간격: ${VIDEO_SEGMENT_DURATION}초"
echo "   해상도: ${VIDEO_WIDTH}x${VIDEO_HEIGHT}"
echo "   타겟 비트레이트: $TARGET_BITRATE (min:$MIN_BITRATE / max:$MAX_BITRATE)"
echo "   RTSP 수신: OpenCV 기본 백엔드"
echo "   FFmpeg 코덱: ${FFMPEG_VIDEO_CODEC} (vsync:${FFMPEG_VSYNC}, preset:${FFMPEG_PRESET})"

echo ""
echo "🚀 실행 준비 완료!"
echo "   개별 실행: cp .env.stream1 .env && python3 run.py"
echo "   전체 실행: ./start_all_streams.sh" 