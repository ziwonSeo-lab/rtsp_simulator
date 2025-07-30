# UDP 패킷 손실 계산 도구

`socket`, `struct`, `argparse`, `time` 모듈만을 사용하여 UDP 패킷의 손실률을 실시간으로 계산하는 도구입니다.

## 파일 구성

- `udp_packet_loss_calculator.py` - UDP 패킷 손실 계산기 (메인 도구)
- `rtsp_rtp_packet_analyzer.py` - RTSP/RTP 스트림 전용 분석기
- `udp_test_sender.py` - 테스트용 UDP 패킷 송신기
- `UDP_PACKET_LOSS_README.md` - 이 파일

## 주요 기능

### UDP 패킷 손실 계산기 (`udp_packet_loss_calculator.py`)

- **실시간 패킷 손실률 계산**: 시퀀스 번호 기반으로 누락된 패킷 감지
- **다양한 패킷 형식 지원**: 
  - Simple 형식 (시퀀스 번호 + 페이로드)
  - RTP 형식 (RTP 헤더의 시퀀스 번호 추출)
- **유연한 설정**:
  - 시퀀스 번호 오프셋 및 크기 조정 가능
  - 바이트 순서 설정 (big-endian/little-endian)
- **상세한 통계 정보**:
  - 수신/예상/손실 패킷 수
  - 손실률, 중복 패킷, 순서 뒤바뀜 감지
  - 실시간 수신률 (packets/sec, KB/sec)
  - 누락된 시퀀스 번호 목록

## 사용법

### 기본 사용법

```bash
# 포트 8000에서 UDP 패킷 수신 및 손실률 계산
python3 udp_packet_loss_calculator.py --port 8000

# RTP 패킷 형식으로 분석
python3 udp_packet_loss_calculator.py --port 8000 --format rtp

# 사용자 정의 시퀀스 설정
python3 udp_packet_loss_calculator.py --port 8000 --seq-offset 4 --seq-size 2 --byte-order little
```

### 매개변수 설명

| 매개변수 | 설명 | 기본값 |
|---------|------|---------|
| `--port` | UDP 수신 포트 번호 | 필수 |
| `--format` | 패킷 형식 (simple/rtp) | simple |
| `--seq-offset` | 시퀀스 번호 오프셋 (바이트) | 0 |
| `--seq-size` | 시퀀스 번호 크기 (1/2/4/8 바이트) | 4 |
| `--byte-order` | 바이트 순서 (big/little) | big |

### 테스트 방법

터미널 1에서 수신기 실행:
```bash
python3 udp_packet_loss_calculator.py --port 9999
```

터미널 2에서 테스트 패킷 전송:
```bash
# 100개 패킷 전송, 5% 손실 시뮬레이션
python3 udp_test_sender.py --port 9999 --count 100 --loss 5

# RTP 형식으로 테스트
python3 udp_test_sender.py --port 9999 --format rtp --count 50
```

## 출력 예시

```
=== UDP 패킷 손실 통계 (실행시간: 15.3초) ===
수신 패킷 수: 95
고유 패킷 수: 95
예상 패킷 수: 100
손실 패킷 수: 5
손실률: 5.00%
중복 패킷: 0
순서 뒤바뀜: 2
시퀀스 범위: 0 ~ 99
총 수신 바이트: 2,850
수신률: 6.2 packets/sec, 0.2 KB/sec
--------------------------------------------------

누락된 시퀀스 번호 (처음 20개):
[15, 32, 48, 67, 83]
```

## 실제 네트워크 환경에서 사용

### RTSP/RTP 스트림 분석

MediaMTX와 같은 RTSP 서버의 RTP 패킷을 분석할 때:

**방법 1: RTSP URL 기반 분석 (권장)**
```bash
# 각 스트림별 분석
python3 rtsp_rtp_packet_analyzer.py --url rtsp://10.2.10.158:1111/live
python3 rtsp_rtp_packet_analyzer.py --url rtsp://10.2.10.158:1112/live
python3 rtsp_rtp_packet_analyzer.py --url rtsp://10.2.10.158:1113/live
python3 rtsp_rtp_packet_analyzer.py --url rtsp://10.2.10.158:1114/live
python3 rtsp_rtp_packet_analyzer.py --url rtsp://10.2.10.158:1115/live
python3 rtsp_rtp_packet_analyzer.py --url rtsp://10.2.10.158:1116/live

# 60초간 분석
python3 rtsp_rtp_packet_analyzer.py --url rtsp://10.2.10.158:1111/live --duration 60
```

**방법 2: 직접 RTP 포트 지정**
```bash
# RTP 패킷 분석 (포트별)
python3 udp_packet_loss_calculator.py --port 8000 --format rtp  # 스트림 1
python3 udp_packet_loss_calculator.py --port 8002 --format rtp  # 스트림 2
python3 udp_packet_loss_calculator.py --port 8004 --format rtp  # 스트림 3
python3 udp_packet_loss_calculator.py --port 8006 --format rtp  # 스트림 4
python3 udp_packet_loss_calculator.py --port 8008 --format rtp  # 스트림 5
python3 udp_packet_loss_calculator.py --port 8010 --format rtp  # 스트림 6
```

### 네트워크 시뮬레이션 환경

tc netem으로 패킷 손실을 시뮬레이션한 환경에서 실제 손실률 측정:

```bash
# veth 인터페이스의 RTP 패킷 분석
python3 udp_packet_loss_calculator.py --port 8002 --format rtp
```

## 특징

1. **경량성**: 표준 라이브러리만 사용하여 의존성 없음
2. **실시간 모니터링**: 5초마다 통계 업데이트
3. **정확성**: 시퀀스 번호 기반의 정확한 손실 계산
4. **유연성**: 다양한 패킷 형식과 설정 지원
5. **상세성**: 패킷 손실뿐만 아니라 중복, 순서 뒤바뀜도 감지

## 주의사항

- 시퀀스 번호가 순환하는 경우 (예: 16비트 RTP 시퀀스) 정확한 분석을 위해 적절한 크기 설정 필요
- 매우 높은 패킷 전송률에서는 시스템 성능에 따라 일부 패킷이 누락될 수 있음
- 방화벽이나 네트워크 설정에서 UDP 포트가 차단되지 않았는지 확인 필요