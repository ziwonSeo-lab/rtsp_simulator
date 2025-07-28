


# 1111~1116 RTSP 포트, 1911~1916 RTMP 포트로 MediaMTX 설정
for i in {0..5}; do
    rtsp_port=$((1111 + i))
    rtmp_port=$((1911 + i))
    
    cat > port_${rtsp_port}.yml << EOF
# MediaMTX 설정 - RTSP:${rtsp_port}, RTMP:${rtmp_port}
rtspAddress: :${rtsp_port}
protocols: [tcp,udp]
rtmpAddress: :${rtmp_port}
hls: false
webrtc: false
srt: false

paths:
  live:
    source: publisher
EOF
    
    echo "MediaMTX 포트 ${rtsp_port} 시작 중..."
    nohup mediamtx port_${rtsp_port}.yml > port_${rtsp_port}.log 2>&1 &
    sleep 2
done



# 6개 MediaMTX 프로세스 확인
echo "실행 중인 MediaMTX: $(ps aux | grep mediamtx | grep -v grep | wc -l)개"

# 1111~1116 RTSP 포트 확인
echo "=== RTSP 포트 1111~1116 상태 ==="
for port in {1111..1116}; do
    printf "포트 %-4s: " "$port"
    nc -z 127.0.0.1 $port && echo "✅ 열림" || echo "❌ 닫힘"
done

# 1911~1916 RTMP 포트 확인  
echo "=== RTMP 포트 1911~1916 상태 ==="
for port in {1911..1916}; do
    printf "포트 %-4s: " "$port"
    nc -z 127.0.0.1 $port && echo "✅ 열림" || echo "❌ 닫힘"
done





## rtsp 송출 실행

sudo python rtsp_sender.py