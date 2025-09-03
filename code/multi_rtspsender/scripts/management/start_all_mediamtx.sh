for i in {0..5}; do
    rtsp_port=$((1111 + i))
    rtmp_port=$((1911 + i))
    rtp_port=$((8000 + i * 2))
    rtcp_port=$((8001 + i * 2))
    webrtc_port=$((9000 + i))
    
    # veth 인터페이스 IP 주소 매핑
    veth_ip="192.168.$((100 + i)).1"
    
    # 경로 계산
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    CONFIG_DIR="$SCRIPT_DIR/../../config/mediamtx"
    LOG_DIR="$SCRIPT_DIR/../../logs"

    mkdir -p "$CONFIG_DIR" "$LOG_DIR"

    # mediamtx 바이너리 확인
    if ! command -v mediamtx >/dev/null 2>&1; then
        echo "❌ mediamtx 바이너리를 찾을 수 없습니다. PATH를 확인하거나 설치하세요."
        echo "   설치 예: wget https://github.com/bluenviron/mediamtx/releases/... ; chmod +x mediamtx ; sudo mv mediamtx /usr/local/bin/"
        exit 1
    fi
    
    cat > "$CONFIG_DIR/port_${rtsp_port}.yml" << EOF
# MediaMTX 설정 - RTSP:${rtsp_port}, RTMP:${rtmp_port}
rtspAddress: :${rtsp_port}
protocols: [tcp,udp]
rtmpAddress: :${rtmp_port}
rtpAddress: :${rtp_port}
rtcpAddress: :${rtcp_port}
webrtcAddress: :${webrtc_port}
hls: false
webrtc: false
srt: false

paths:
  live:
    source: publisher
EOF
    
    echo "MediaMTX 포트 ${rtsp_port} 시작 중..."
    nohup mediamtx "$CONFIG_DIR/port_${rtsp_port}.yml" > "$LOG_DIR/port_${rtsp_port}.log" 2>&1 &
    sleep 2

done