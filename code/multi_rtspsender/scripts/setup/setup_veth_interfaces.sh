#!/bin/bash

# veth 인터페이스 생성 및 tc netem 설정 스크립트

echo "=== veth 인터페이스 생성 및 tc netem 설정 ==="

# 기존 veth 인터페이스 정리
for i in {0..5}; do
    sudo ip link del veth$i 2>/dev/null || true
    sudo ip link del peer$i 2>/dev/null || true
done

sleep 2

# veth 인터페이스 생성
for i in {0..5}; do
    veth_name="veth$i"
    peer_name="peer$i"
    veth_ip="192.168.$((100 + i)).1"
    peer_ip="192.168.$((100 + i)).2"
    
    echo "[$((i+1))/6] $veth_name 인터페이스 생성 중..."
    
    # veth pair 생성
    sudo ip link add $veth_name type veth peer name $peer_name
    
    # IP 주소 할당
    sudo ip addr add ${veth_ip}/24 dev $veth_name
    sudo ip addr add ${peer_ip}/24 dev $peer_name
    
    # 인터페이스 활성화
    sudo ip link set $veth_name up
    sudo ip link set $peer_name up
    
    echo "  - $veth_name: $veth_ip/24"
    echo "  - $peer_name: $peer_ip/24"
done

sleep 2

echo
echo "=== tc netem 설정 적용 ==="

# tc netem 설정
tc_configs=(
    "0:기본설정"
    "1:delay 300ms 25ms loss 2%"
    "2:delay 5ms 50ms loss 5%"
    "3:rate 5mbit delay 150ms 75ms loss 8%"
    "4:rate 3mbit delay 200ms 100ms loss 10%"
    "5:rate 2mbit delay 300ms 150ms loss 15%"
)

for config in "${tc_configs[@]}"; do
    i=$(echo $config | cut -d':' -f1)
    setting=$(echo $config | cut -d':' -f2)
    
    echo "[$((i+1))/6] veth$i tc 설정: $setting"
    
    if [ $i -eq 0 ]; then
        # 기본 설정 (netem만)
        sudo tc qdisc add dev veth$i root netem limit 1000
    elif [ $i -le 2 ]; then
        # 지연 및 손실만
        if [ $i -eq 1 ]; then
            sudo tc qdisc add dev veth$i root netem delay 300ms 25ms loss 2% limit 1000
        else
            sudo tc qdisc add dev veth$i root netem delay 5ms 50ms loss 5% limit 1000
        fi
    else
        # 대역폭 제한 + netem
        if [ $i -eq 3 ]; then
            sudo tc qdisc add dev veth$i root tbf rate 5mbit burst 32000b lat 825s
            sudo tc qdisc add dev veth$i parent 1:1 netem delay 150ms 75ms loss 8% limit 1000
        elif [ $i -eq 4 ]; then
            sudo tc qdisc add dev veth$i root tbf rate 3mbit burst 31999b lat 4240s
            sudo tc qdisc add dev veth$i parent 1:1 netem delay 200ms 100ms loss 10% limit 1000
        else
            sudo tc qdisc add dev veth$i root tbf rate 2mbit burst 32000b lat 4210s
            sudo tc qdisc add dev veth$i parent 1:1 netem delay 300ms 150ms loss 15% limit 1000
        fi
    fi
done

echo
echo "=== 설정 확인 ==="

for i in {0..5}; do
    echo "veth$i 상태:"
    ip addr show veth$i | grep "inet " | head -1
    tc qdisc show dev veth$i
    echo
done

echo "✅ veth 인터페이스 및 tc netem 설정 완료!"