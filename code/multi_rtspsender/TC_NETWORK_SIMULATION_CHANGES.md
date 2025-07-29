# TC Network Simulation Changes

## 🛠️ Problem Fixed

The original `rtsp_sender.py` had a fundamental architectural issue:
- **Previous**: Applied tc settings to virtual veth interfaces that had no effect on actual traffic
- **Current**: Applies tc settings to the real network interface (loopback) where MediaMTX traffic flows

## 🔧 Key Changes Made

### 1. NetworkSimulator Class Refactored

**Before:**
```python
def setup_virtual_interface(stream_id, target_ip, target_port):
    # Created veth pairs that isolated traffic from tc effects
    
def apply_network_conditions(...):
    # Applied tc to veth interfaces (ineffective)
```

**After:**
```python
def setup_network_simulation(stream_id, target_ip, target_port):
    # Prepares tc handles for real network interface
    
def apply_network_conditions(...):
    # Applies tc to loopback interface with port-based filtering
```

### 2. Real Network Interface Usage

- **Interface**: Changed from virtual `veth{N}` to real `lo` (loopback)
- **Traffic Control**: Uses HTB (Hierarchical Token Bucket) + netem for precise control
- **Port Filtering**: Applies tc rules based on RTMP port numbers (1911-1916)

### 3. TC Architecture

```
lo interface:
├── HTB root qdisc (1:)
├── HTB classes per stream (1:10, 1:11, 1:12, ...)
├── netem qdiscs per stream (20:, 21:, 22:, ...)
└── Port-based filters (sport 1911, 1912, 1913, ...)
```

## 📋 Technical Implementation

### Stream-to-Port Mapping
```
Stream 0: RTMP 1911, tc class 1:10, netem 20:
Stream 1: RTMP 1912, tc class 1:11, netem 21:
Stream 2: RTMP 1913, tc class 1:12, netem 22:
Stream 3: RTMP 1914, tc class 1:13, netem 23:
Stream 4: RTMP 1915, tc class 1:14, netem 24:
Stream 5: RTMP 1916, tc class 1:15, netem 25:
```

### Network Conditions Applied
- **Packet Loss**: netem loss parameter
- **Network Delay**: netem delay parameter  
- **Jitter**: netem delay variation
- **Bandwidth Limiting**: HTB rate/ceil parameters

## 🧪 Testing Instructions

### 1. System Requirements
```bash
# Check tc availability
/usr/sbin/tc -help

# Check sudo permissions
sudo -n true

# Check FFmpeg
ffmpeg -version
```

### 2. Start MediaMTX Servers
```bash
cd /home/szw001/development/2025/IUU/rtsp_simulator/code/multi_rtspsender/scripts/management
./start_all_mediamtx.sh
```

### 3. Test Baseline (No Network Simulation)
```bash
cd /home/szw001/development/2025/IUU/rtsp_simulator/code/multi_rtspsender/tests/integration
python3 test_current_streams.py --stream 1 --duration 10
# Expected: 0.00% packet loss
```

### 4. Start RTSP Sender with TC Network Simulation
```bash
cd /home/szw001/development/2025/IUU/rtsp_simulator/code/multi_rtspsender
sudo python3 src/server/rtsp_sender.py -c config.json
```

### 5. Test Network Simulation Effects
```bash
# Test stream 1 (2% loss, 300ms delay)
python3 test_current_streams.py --stream 2 --duration 30

# Expected results based on config.json:
# Stream 1 (port 1112): ~2% packet loss, ~300ms delay
# Stream 2 (port 1113): ~5% packet loss, ~5ms delay  
# Stream 3 (port 1114): ~8% packet loss, ~150ms delay, 5Mbps limit
# Stream 4 (port 1115): ~10% packet loss, ~200ms delay, 3Mbps limit
# Stream 5 (port 1116): ~15% packet loss, ~300ms delay, 2Mbps limit
```

### 6. Verify TC Settings
```bash
# Check tc configuration
sudo tc qdisc show dev lo
sudo tc class show dev lo  
sudo tc filter show dev lo

# Should show HTB classes and netem qdiscs for active streams
```

## 📊 Expected Results

### Baseline (Stream 0)
```
=== RTP 패킷 손실 통계 ===
손실률: 0.00%
수신률: ~540 packets/sec
```

### With Network Simulation (Stream 1)
```
=== RTP 패킷 손실 통계 ===
손실률: ~2.00% (±0.5%)
수신률: ~530 packets/sec (reduced due to loss)
지연: ~300ms (measurable in timestamps)
```

## 🚨 Important Notes

1. **Sudo Required**: TC commands require root privileges
2. **Real Network Effects**: This now affects actual packet transmission
3. **Port-Based Filtering**: Only affects specified RTMP ports
4. **Cleanup**: TC settings are properly cleaned up on exit

## 🔍 Troubleshooting

### Common Issues

**"tc command not found"**
```bash
sudo apt install iproute2
```

**"Permission denied"**
```bash
sudo python3 src/server/rtsp_sender.py
```

**"Address already in use"**
```bash
# Kill existing MediaMTX
pkill mediamtx
./scripts/management/start_all_mediamtx.sh
```

### Verify TC is Working
```bash
# Before starting sender
tc qdisc show dev lo
# Output: qdisc noqueue 0: root refcnt 2

# After starting sender  
sudo tc qdisc show dev lo
# Output: Should show HTB and netem qdiscs
```

## ✅ Success Criteria

1. **TC Settings Applied**: `tc qdisc show dev lo` shows HTB + netem
2. **Port Filtering Active**: `tc filter show dev lo` shows port-based rules
3. **Measurable Packet Loss**: RTSP client reports configured loss rates
4. **Network Delay Observable**: Timestamps show increased latency
5. **Bandwidth Limiting**: Throughput matches configured limits

## 🎯 Next Steps

1. Test with actual video streaming
2. Validate packet loss measurements match tc settings
3. Compare against baseline streams
4. Document performance characteristics
5. Add automated test suite for tc validation