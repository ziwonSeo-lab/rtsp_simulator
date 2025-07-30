# veth 인터페이스 수동 설정 가이드

RTSP 클라이언트에서 tc netem 효과를 측정하기 위해 veth 인터페이스를 수동으로 설정해야 합니다.

## 🔧 1단계: veth 인터페이스 생성

터미널에서 다음 명령어들을 **순서대로** 실행하세요:

```bash
# 기존 veth 인터페이스 정리 (에러가 나도 괜찮음)
for i in {0..5}; do
    sudo ip link del veth$i 2>/dev/null || true
    sudo ip link del peer$i 2>/dev/null || true
done

# veth 인터페이스 생성
for i in {0..5}; do
    veth_name="veth$i"
    peer_name="peer$i"
    veth_ip="192.168.$((100 + i)).1"
    peer_ip="192.168.$((100 + i)).2"
    
    echo "생성 중: $veth_name"
    sudo ip link add $veth_name type veth peer name $peer_name
    sudo ip addr add ${veth_ip}/24 dev $veth_name
    sudo ip addr add ${peer_ip}/24 dev $peer_name
    sudo ip link set $veth_name up
    sudo ip link set $peer_name up
done
```

## ⚙️ 2단계: tc netem 설정

```bash
# veth0: 기본 설정
sudo tc qdisc add dev veth0 root netem limit 1000

# veth1: 지연 300ms, 손실 2%
sudo tc qdisc add dev veth1 root netem delay 300ms 25ms loss 2% limit 1000

# veth2: 지연 5ms, 손실 5%
sudo tc qdisc add dev veth2 root netem delay 5ms 50ms loss 5% limit 1000

# veth3: 5Mbps + 지연 150ms + 손실 8%
sudo tc qdisc add dev veth3 root tbf rate 5mbit burst 32000b lat 825s
sudo tc qdisc add dev veth3 parent 1:1 netem delay 150ms 75ms loss 8% limit 1000

# veth4: 3Mbps + 지연 200ms + 손실 10%
sudo tc qdisc add dev veth4 root tbf rate 3mbit burst 31999b lat 4240s
sudo tc qdisc add dev veth4 parent 1:1 netem delay 200ms 100ms loss 10% limit 1000

# veth5: 2Mbps + 지연 300ms + 손실 15%
sudo tc qdisc add dev veth5 root tbf rate 2mbit burst 32000b lat 4210s
sudo tc qdisc add dev veth5 parent 1:1 netem delay 300ms 150ms loss 15% limit 1000
```

## ✅ 3단계: 설정 확인

```bash
# veth 인터페이스 확인
for i in {0..5}; do
    echo "=== veth$i ==="
    ip addr show veth$i | grep "inet "
    tc qdisc show dev veth$i
    echo
done
```

## 🧪 4단계: 테스트 실행

설정이 완료되면 다음 명령어로 테스트할 수 있습니다:

```bash
# 각 스트림별 개별 테스트
python3 test_stream_with_veth.py --veth 0 --duration 10  # 기본 (0% 손실)
python3 test_stream_with_veth.py --veth 1 --duration 10  # 2% 손실
python3 test_stream_with_veth.py --veth 2 --duration 10  # 5% 손실
python3 test_stream_with_veth.py --veth 3 --duration 10  # 8% 손실
python3 test_stream_with_veth.py --veth 4 --duration 10  # 10% 손실
python3 test_stream_with_veth.py --veth 5 --duration 10  # 15% 손실
```

## 📊 예상 결과

각 veth 인터페이스의 tc 설정에 따라 다음과 같은 패킷 손실률이 측정되어야 합니다:

- **veth0**: ~0% 손실률
- **veth1**: ~2% 손실률
- **veth2**: ~5% 손실률  
- **veth3**: ~8% 손실률
- **veth4**: ~10% 손실률
- **veth5**: ~15% 손실률

## ⚠️ 문제 해결

만약 veth 인터페이스 설정에 문제가 있다면:

1. `ip link show | grep veth` 로 인터페이스 확인
2. `tc qdisc show` 로 tc 설정 확인
3. 필요시 `sudo ip link del veth0` 등으로 개별 삭제 후 재생성