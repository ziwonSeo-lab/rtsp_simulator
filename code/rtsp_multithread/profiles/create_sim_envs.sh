#!/bin/bash
set -euo pipefail

# 시뮬레이터 전용 .env 생성 스크립트 (profiles/sim)
# 사용법: ./profiles/create_sim_envs.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROFILE_DIR="$SCRIPT_DIR/sim"
mkdir -p "$PROFILE_DIR"

# 기본값 (환경변수로 오버라이드 가능)
SIM_BASE_IP="${SIM_BASE_IP:-10.2.10.158}"
SIM_START_PORT="${SIM_START_PORT:-1111}"

for i in {1..6}; do
  port=$((SIM_START_PORT + i - 1))
  RTSP_URL="rtsp://${SIM_BASE_IP}:${port}/live"
  cat > "$PROFILE_DIR/.env.stream${i}" <<EOF
RTSP_URL=${RTSP_URL}
VESSEL_NAME=vesselTest
STREAM_NUMBER=${i}
# 카메라 식별자 (필요에 맞게 수정해서 사용)
CAMERA_ID=${CAMERA_ID:-${i}}
CAMERA_NAME=${CAMERA_NAME:-camera${i}}
TEMP_OUTPUT_PATH=./output/temp/
FINAL_OUTPUT_PATH=/mnt/raid5
DEFAULT_INPUT_FPS=15.0
VIDEO_SEGMENT_DURATION=20
VIDEO_WIDTH=1920
VIDEO_HEIGHT=1080
ENABLE_MONITORING=true
EOF
done

echo "✅ profiles/sim/.env.stream{1..6} 생성 완료" 