for i in {0..5}; do
    rtsp_port=$((1111 + i))
    rtmp_port=$((1911 + i))
    rtp_port=$((8000 + i * 2))
    rtcp_port=$((8001 + i * 2))
    webrtc_port=$((9000 + i))
    
    # veth 인터페이스 IP 주소 매핑
    veth_ip="192.168.$((100 + i)).1"
    
    cat > ../../config/mediamtx/port_${rtsp_port}.yml << EOF
# MediaMTX 설정 - RTSP:${rtsp_port}, RTMP:${rtmp_port}
rtspAddress: :${rtsp_port}
protocols: [udp]
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
    nohup mediamtx ../../config/mediamtx/port_${rtsp_port}.yml > ../../logs/port_${rtsp_port}.log 2>&1 &
    sleep 2
done