#!/bin/bash
set -euo pipefail

# 카메라/시뮬레이터 혼합용 .env 생성 스크립트 (profiles/camera)
# 사용법: ./profiles/create_camera_envs.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
PROFILE_DIR="$SCRIPT_DIR/camera"
mkdir -p "$PROFILE_DIR"

# 기본값들 (필요시 환경변수로 오버라이드)
CAM_USER="${CAM_USER:-root}"
CAM_PASS="${CAM_PASS:-root}"
CAM_BASE="${CAM_BASE:-192.168.1}"
CAM_START_HOST="${CAM_START_HOST:-100}"
SIM_BASE_IP="${SIM_BASE_IP:-10.2.10.158}"
SIM_START_PORT="${SIM_START_PORT:-1111}"

for i in {1..6}; do
  if [ $i -le 4 ]; then
    host=$((CAM_START_HOST + i))
    RTSP_URL="rtsp://${CAM_USER}:${CAM_PASS}@${CAM_BASE}.${host}:554/cam0_0"
  else
    port=$((SIM_START_PORT + i - 1))
    RTSP_URL="rtsp://${SIM_BASE_IP}:${port}/live"
  fi
  cat > "$PROFILE_DIR/.env.stream${i}" <<EOF
RTSP_URL=${RTSP_URL}
VESSEL_NAME=vesselTest
STREAM_NUMBER=${i}
# 카메라 식별자 (필요에 맞게 수정해서 사용)
CAMERA_ID=${CAMERA_ID:-${i}}
CAMERA_NAME=${CAMERA_NAME:-camera${i}}
TEMP_OUTPUT_PATH=./output/temp/
FINAL_OUTPUT_PATH=/mnt/raid5/cam
LOG_DIR=/mnt/raid5/logs
DEFAULT_INPUT_FPS=15.0
VIDEO_SEGMENT_DURATION=300
VIDEO_WIDTH=1920
VIDEO_HEIGHT=1080
ENABLE_MONITORING=true
LOG_LEVEL=INFO
EOF
done

echo "✅ profiles/camera/.env.stream{1..6} 생성 완료" 