#!/bin/bash

# 네트워크 시뮬레이션 테스트 스크립트
# veth 인터페이스를 통한 RTSP 스트림 패킷 손실률 분석

echo "=== veth 인터페이스를 통한 네트워크 시뮬레이션 테스트 ==="
echo "각 veth 인터페이스의 tc netem 설정에 따른 패킷 손실률 측정"
echo

# veth 인터페이스 IP 및 네트워크 설정 정보
declare -A veth_info=(
    [0]="192.168.100.1,기본설정(손실없음)"
    [1]="192.168.101.1,지연300ms+손실2%"
    [2]="192.168.102.1,지연5ms+손실5%"  
    [3]="192.168.103.1,5Mbps+지연150ms+손실8%"
    [4]="192.168.104.1,3Mbps+지연200ms+손실10%"
    [5]="192.168.105.1,2Mbps+지연300ms+손실15%"
)

# 각 veth 인터페이스를 통한 연결 테스트
for i in {0..5}; do
    rtsp_port=$((1111 + i))
    veth_data=${veth_info[$i]}
    veth_ip=$(echo $veth_data | cut -d',' -f1)
    tc_setting=$(echo $veth_data | cut -d',' -f2)
    
    echo "[$((i+1))/6] 스트림 $((i+1)) - veth$i 테스트"
    echo "----------------------------------------"
    echo "veth IP: $veth_ip"
    echo "RTSP 포트: $rtsp_port"
    echo "tc 설정: $tc_setting"
    echo
    
    # veth 인터페이스를 통한 연결을 위해 라우팅 추가
    echo "임시 라우팅 설정 중..."
    
    # 기존 라우팅 백업
    original_route=$(ip route get 10.2.10.158 2>/dev/null)
    
    # veth 인터페이스를 통한 라우팅 추가
    sudo ip route add 10.2.10.158/32 via $veth_ip dev veth$i 2>/dev/null || \
    sudo ip route replace 10.2.10.158/32 via $veth_ip dev veth$i
    
    echo "RTSP 클라이언트로 10초간 패킷 분석..."
    
    # RTSP 클라이언트 실행 (10초간)
    timeout 15s python3 rtsp_client_packet_analyzer.py \
        --url rtsp://10.2.10.158:$rtsp_port/live \
        --duration 10 2>/dev/null || echo "연결 실패 또는 타임아웃"
    
    # 라우팅 복원
    echo "라우팅 복원 중..."
    sudo ip route del 10.2.10.158/32 2>/dev/null || true
    
    echo
    echo "=========================================="
    echo
    
    # 다음 테스트 전 대기
    sleep 2
done

echo "전체 네트워크 시뮬레이션 테스트 완료!"
echo
echo "=== 예상 결과 요약 ==="
echo "스트림 1 (veth0): 손실률 ~0%"
echo "스트림 2 (veth1): 손실률 ~2%"  
echo "스트림 3 (veth2): 손실률 ~5%"
echo "스트림 4 (veth3): 손실률 ~8%"
echo "스트림 5 (veth4): 손실률 ~10%"
echo "스트림 6 (veth5): 손실률 ~15%"