# 📁 Multi RTSP Sender 프로젝트 구조

## 🌟 프로젝트 개요
RTSP 스트리밍 환경에서 네트워크 품질 시뮬레이션 및 패킷 손실률 분석을 위한 통합 도구 모음

---

## 📂 디렉토리 구조

```
multi_rtspsender/
├── 📚 docs/                   # 문서 및 가이드
├── ⚙️ config/                 # 설정 파일들
├── 🎯 src/                    # 핵심 소스코드
├── 🔧 scripts/                # 실행 스크립트들
├── 🧪 tests/                  # 테스트 도구들
├── 🛠️ tools/                  # 유틸리티 도구들
└── 📊 logs/                   # 로그 파일들
```

---

## 📚 docs/ - 문서 및 가이드

| 파일명 | 설명 | 사용 시점 |
|--------|------|-----------|
| `README.md` | 프로젝트 전체 개요 | 프로젝트 시작 시 |
| `manual_veth_setup.md` | **⭐ veth 네트워크 시뮬레이션 설정 가이드** | 환경 설정 시 |
| `UDP_PACKET_LOSS_README.md` | UDP 패킷 손실 계산 도구 사용법 | UDP 도구 사용 시 |

---

## ⚙️ config/ - 설정 파일들

### config/
- `config.json` - RTSP 송출기 메인 설정

### config/mediamtx/
- `port_1111.yml ~ port_1116.yml` - **6개 MediaMTX 서버 개별 설정**
- `mediamtx_stream0.yml ~ stream5.yml` - 스트림별 상세 설정

### config/network/
- 네트워크 시뮬레이션 관련 설정 (향후 확장)

---

## 🎯 src/ - 핵심 소스코드

### src/server/ - RTSP 서버/송출 관련
| 파일명 | 설명 | 주요 기능 |
|--------|------|-----------|
| `rtsp_sender.py` | **⭐ 메인 RTSP 송출기** | tc netem 기반 다중 스트림 송출 |
| `rtsp_sender_tc.py` | tc 전용 RTSP 송출기 | 대체 송출 도구 |
| `rtsp_server_win.py` | Windows용 RTSP 서버 | Windows 환경 지원 |

### src/client/ - RTSP 클라이언트 관련
| 파일명 | 설명 | 주요 기능 |
|--------|------|-----------|
| `rtsp_client_packet_analyzer.py` | **⭐ 핵심 RTSP 클라이언트 + 패킷 분석기** | RTSP 연결, RTP 패킷 손실률 측정 |

### src/analysis/ - 패킷 분석 관련
| 파일명 | 설명 | 주요 기능 |
|--------|------|-----------|
| `rtsp_rtp_packet_analyzer.py` | RTSP/RTP 전용 분석기 (구버전) | 기본적인 RTP 패킷 분석 |

---

## 🔧 scripts/ - 실행 스크립트들

### scripts/setup/ - 환경 설정 스크립트
| 파일명 | 설명 | 사용법 |
|--------|------|--------|
| `setup_veth_interfaces.sh` | **⭐ veth 인터페이스 + tc netem 자동 설정** | `./setup_veth_interfaces.sh` |

### scripts/management/ - 서버 관리 스크립트
| 파일명 | 설명 | 사용법 |
|--------|------|--------|
| `start_all_mediamtx.sh` | **⭐ 6개 MediaMTX 서버 일괄 시작** | `./start_all_mediamtx.sh` |
| `stop_all_mediamtx.sh` | MediaMTX 서버 일괄 종료 | `./stop_all_mediamtx.sh` |

---

## 🧪 tests/ - 테스트 도구들

### tests/integration/ - 통합 테스트
| 파일명 | 설명 | 사용법 |
|--------|------|--------|
| `test_stream_with_veth.py` | **⭐ veth별 개별 스트림 테스트** | `python3 test_stream_with_veth.py --veth 1` |
| `test_current_streams.py` | 현재 스트림 상태 기본 테스트 | `python3 test_current_streams.py` |
| `test_network_simulation.sh` | 네트워크 시뮬레이션 통합 테스트 | `./test_network_simulation.sh` |
| `test_all_streams.sh` | 전체 스트림 순차 테스트 | `./test_all_streams.sh` |

### tests/unit/ - 단위 테스트
- 향후 단위 테스트 파일들 추가 예정

---

## 🛠️ tools/ - 유틸리티 도구들

### tools/udp/ - UDP 관련 도구
| 파일명 | 설명 | 사용법 |
|--------|------|--------|
| `udp_packet_loss_calculator.py` | 범용 UDP 패킷 손실 계산기 | `python3 udp_packet_loss_calculator.py --port 8000` |
| `udp_test_sender.py` | UDP 테스트 패킷 송신기 | `python3 udp_test_sender.py --port 8000` |

### tools/utils/ - 기타 유틸리티
- `.video/` - 테스트용 비디오 파일들

---

## 📊 logs/ - 로그 파일들

- `rtsp_sender*.log` - RTSP 송출기 로그들
- `nohup.out` - 백그라운드 실행 로그
- 기타 실행 로그들

---

## 🚀 빠른 시작 가이드

### 1단계: 환경 설정
```bash
# veth 인터페이스 + tc netem 설정
./scripts/setup/setup_veth_interfaces.sh

# 또는 수동 설정 (docs/manual_veth_setup.md 참조)
```

### 2단계: MediaMTX 서버 시작
```bash
./scripts/management/start_all_mediamtx.sh
```

### 3단계: 스트림 송출
```bash
sudo python3 src/server/rtsp_sender.py
```

### 4단계: 패킷 손실률 테스트
```bash
# veth1을 통한 스트림 테스트 (2% 손실 예상)
python3 tests/integration/test_stream_with_veth.py --veth 1 --duration 30

# 직접 RTSP 클라이언트 실행
python3 src/client/rtsp_client_packet_analyzer.py --url rtsp://10.2.10.158:1111/live
```

---

## 🎯 핵심 파일 우선순위

### ⭐ 가장 중요한 파일들 (반드시 숙지)
1. **`src/client/rtsp_client_packet_analyzer.py`** - 패킷 분석의 핵심
2. **`docs/manual_veth_setup.md`** - 네트워크 시뮬레이션 설정 가이드
3. **`tests/integration/test_stream_with_veth.py`** - veth별 테스트 실행
4. **`scripts/management/start_all_mediamtx.sh`** - MediaMTX 서버 구동

### 🔧 설정/관리 파일들
5. **`scripts/setup/setup_veth_interfaces.sh`** - 자동 veth 설정
6. **`config/mediamtx/port_*.yml`** - MediaMTX 개별 설정
7. **`src/server/rtsp_sender.py`** - 스트림 송출

---

## 🌟 주요 특징

- **6개 독립 스트림**: 서로 다른 네트워크 조건 시뮬레이션
- **완전한 RTSP 구현**: DESCRIBE, SETUP, PLAY, TEARDOWN 지원
- **정확한 패킷 분석**: RTP 시퀀스 번호 기반 손실률 계산
- **네트워크 시뮬레이션**: tc netem + veth 기반 실제 네트워크 품질 재현
- **통합 테스트 환경**: 개별/통합 테스트 도구 완비