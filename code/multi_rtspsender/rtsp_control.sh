#!/usr/bin/env bash
#
# rtsp_control.sh — MediaMTX + RTSP 송출기 통합 관리 스크립트
#
# 단일 진입점으로 MediaMTX 인스턴스와 RTSP 송출기를 한 번에 기동/종료/재시작한다.
# 설정은 config/config.json 하나만 사용하며, MediaMTX의 .yml은 여기서 자동 생성한다.
#
# 사용법:
#   ./rtsp_control.sh start     # MediaMTX → 송출기 순서로 기동
#   ./rtsp_control.sh stop      # 송출기 → MediaMTX 순서로 종료 + tc 정리
#   ./rtsp_control.sh restart   # 완전 종료 후 재기동
#   ./rtsp_control.sh status    # 현재 상태 확인 (부분 생존 감지 포함)
#
# 특징:
#   - start 는 항상 먼저 stop 을 호출하여 좀비/부분 생존 프로세스를 정리한다.
#   - config.json 의 enabled 스트림만 대상으로 한다.
#   - 송출기는 sudo 로 실행하여 종료 시 tc(netem) 설정이 정상 정리되도록 한다.

set -uo pipefail

# --- 경로 설정 ----------------------------------------------------------------
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="${BASE_DIR}/config/config.json"
SENDER="${BASE_DIR}/src/server/rtsp_sender.py"
MTX_CONF_DIR="${BASE_DIR}/config/mediamtx"
RUN_DIR="${BASE_DIR}/run"
LOG_DIR="${BASE_DIR}/logs"
SENDER_PIDFILE="${RUN_DIR}/sender.pid"

MEDIAMTX_BIN="$(command -v mediamtx || echo /usr/local/bin/mediamtx)"

# 종료 시 SIGTERM 후 SIGKILL 까지 대기 시간(초)
TERM_WAIT=10
# MediaMTX RTMP 포트 열림 대기 시간(초)
PORT_WAIT=15

# --- 출력 헬퍼 ----------------------------------------------------------------
c_reset=$'\033[0m'; c_red=$'\033[31m'; c_grn=$'\033[32m'; c_ylw=$'\033[33m'; c_blu=$'\033[34m'
info() { echo "${c_blu}[INFO]${c_reset} $*"; }
ok()   { echo "${c_grn}[ OK ]${c_reset} $*"; }
warn() { echo "${c_ylw}[WARN]${c_reset} $*"; }
err()  { echo "${c_red}[FAIL]${c_reset} $*" >&2; }

# --- 사전 점검 ----------------------------------------------------------------
preflight() {
    local missing=0
    [[ -f "$CONFIG" ]]      || { err "설정 파일 없음: $CONFIG"; missing=1; }
    [[ -f "$SENDER" ]]      || { err "송출기 없음: $SENDER"; missing=1; }
    [[ -x "$MEDIAMTX_BIN" ]] || { err "mediamtx 바이너리 없음: $MEDIAMTX_BIN"; missing=1; }
    command -v jq      >/dev/null || { err "jq 미설치: sudo apt install jq"; missing=1; }
    command -v python3 >/dev/null || { err "python3 미설치"; missing=1; }
    command -v ffmpeg  >/dev/null || { err "ffmpeg 미설치: sudo apt install ffmpeg"; missing=1; }
    [[ "$missing" -eq 0 ]] || exit 1
    mkdir -p "$RUN_DIR" "$LOG_DIR" "$MTX_CONF_DIR"
}

# config.json 에서 enabled 스트림의 "rtsp_port rtmp_port" 목록을 출력
read_streams() {
    jq -r '.streams[] | select(.enabled == true) | "\(.rtsp_port) \(.rtmp_port)"' "$CONFIG"
}

# --- MediaMTX 설정 자동 생성 ---------------------------------------------------
gen_mediamtx_config() {
    local rtsp_port="$1" rtmp_port="$2"
    local rtp_port=$(( 8000 + (rtsp_port - 1111) * 2 ))
    local rtcp_port=$(( rtp_port + 1 ))
    local webrtc_port=$(( 9000 + (rtsp_port - 1111) ))
    local conf="${MTX_CONF_DIR}/port_${rtsp_port}.yml"

    cat > "$conf" <<EOF
# 자동 생성됨 (rtsp_control.sh) — 직접 수정 금지. config.json 을 수정하세요.
# RTSP:${rtsp_port}, RTMP:${rtmp_port}
rtspAddress: :${rtsp_port}
protocols: [tcp, udp]
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
    echo "$conf"
}

# --- 포트 열림 대기 ------------------------------------------------------------
wait_for_port() {
    local port="$1" elapsed=0
    while ! (exec 3<>"/dev/tcp/127.0.0.1/${port}") 2>/dev/null; do
        exec 3>&- 2>/dev/null || true
        sleep 0.5
        elapsed=$(( elapsed + 1 ))
        if [[ $(( elapsed / 2 )) -ge "$PORT_WAIT" ]]; then
            return 1
        fi
    done
    exec 3>&- 2>/dev/null || true
    return 0
}

# --- 프로세스 종료 헬퍼 (SIGTERM → 대기 → SIGKILL) -----------------------------
# 인자: <pid> [sudo]
kill_graceful() {
    local pid="$1" use_sudo="${2:-}"
    local KILL=(kill)
    [[ "$use_sudo" == "sudo" ]] && KILL=(sudo kill)

    if ! { kill -0 "$pid" 2>/dev/null || sudo kill -0 "$pid" 2>/dev/null; }; then
        return 0  # 이미 죽음
    fi

    "${KILL[@]}" -TERM "$pid" 2>/dev/null || true
    local waited=0
    while { kill -0 "$pid" 2>/dev/null || sudo kill -0 "$pid" 2>/dev/null; }; do
        sleep 1
        waited=$(( waited + 1 ))
        if [[ "$waited" -ge "$TERM_WAIT" ]]; then
            warn "PID $pid SIGTERM 무응답 → SIGKILL"
            "${KILL[@]}" -KILL "$pid" 2>/dev/null || true
            break
        fi
    done
}

# --- tc(netem) 잔여 설정 정리 (안전망) -----------------------------------------
cleanup_tc() {
    # 송출기가 정상 종료되면 스스로 정리하지만, 강제 종료에 대비한 안전망.
    # 이 시스템은 loopback(lo) 에만 tc 를 적용한다.
    if sudo tc qdisc show dev lo 2>/dev/null | grep -q htb; then
        info "loopback tc 잔여 설정 제거"
        sudo tc qdisc del dev lo root 2>/dev/null || true
    fi
}

# --- 송출기 종료 ---------------------------------------------------------------
stop_sender() {
    local stopped=0
    # 1) PID 파일 기반
    if [[ -f "$SENDER_PIDFILE" ]]; then
        local pid; pid="$(cat "$SENDER_PIDFILE" 2>/dev/null || true)"
        if [[ -n "$pid" ]]; then
            info "송출기 종료 (PID $pid)"
            kill_graceful "$pid" sudo
            stopped=1
        fi
        rm -f "$SENDER_PIDFILE"
    fi
    # 2) 이름 기반 잔여 정리 (부분 생존 대비)
    if pgrep -f "rtsp_sender.py" >/dev/null 2>&1; then
        warn "잔여 송출기 프로세스 정리"
        sudo pkill -TERM -f "rtsp_sender.py" 2>/dev/null || true
        sleep 2
        sudo pkill -KILL -f "rtsp_sender.py" 2>/dev/null || true
        stopped=1
    fi
    [[ "$stopped" -eq 1 ]] && ok "송출기 종료 완료" || info "실행 중인 송출기 없음"
}

# --- MediaMTX 종료 -------------------------------------------------------------
stop_mediamtx() {
    local stopped=0
    # 1) PID 파일 기반
    shopt -s nullglob
    for pf in "${RUN_DIR}"/mediamtx_*.pid; do
        local pid; pid="$(cat "$pf" 2>/dev/null || true)"
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            kill_graceful "$pid"
            stopped=1
        fi
        rm -f "$pf"
    done
    shopt -u nullglob
    # 2) 이름 기반 잔여 정리
    if pgrep -f "$MEDIAMTX_BIN" >/dev/null 2>&1 || pgrep -x mediamtx >/dev/null 2>&1; then
        warn "잔여 MediaMTX 프로세스 정리"
        pkill -TERM -f mediamtx 2>/dev/null || true
        sleep 2
        pkill -KILL -f mediamtx 2>/dev/null || true
        stopped=1
    fi
    [[ "$stopped" -eq 1 ]] && ok "MediaMTX 종료 완료" || info "실행 중인 MediaMTX 없음"
}

# --- 통합 종료 -----------------------------------------------------------------
do_stop() {
    info "===== 종료 시작 ====="
    stop_sender      # 송출기 먼저 (tc 정리를 위해)
    stop_mediamtx    # 그다음 서버
    cleanup_tc       # 잔여 tc 안전망
    ok "===== 종료 완료 ====="
}

# --- MediaMTX 기동 -------------------------------------------------------------
start_mediamtx() {
    info "MediaMTX 인스턴스 기동"
    local count=0
    while read -r rtsp_port rtmp_port; do
        [[ -z "$rtsp_port" ]] && continue
        local conf; conf="$(gen_mediamtx_config "$rtsp_port" "$rtmp_port")"
        local log="${LOG_DIR}/mediamtx_${rtsp_port}.log"
        nohup "$MEDIAMTX_BIN" "$conf" > "$log" 2>&1 &
        echo "$!" > "${RUN_DIR}/mediamtx_${rtsp_port}.pid"
        info "  MediaMTX RTSP:${rtsp_port} / RTMP:${rtmp_port} (PID $!)"
        count=$(( count + 1 ))
    done < <(read_streams)

    if [[ "$count" -eq 0 ]]; then
        err "enabled 스트림이 없습니다. config.json 을 확인하세요."
        return 1
    fi

    # RTMP 포트 readiness 대기 (송출기가 헬스체크하므로 필수)
    info "MediaMTX RTMP 포트 준비 대기"
    while read -r rtsp_port rtmp_port; do
        [[ -z "$rtmp_port" ]] && continue
        if wait_for_port "$rtmp_port"; then
            ok "  RTMP:${rtmp_port} 준비됨"
        else
            err "  RTMP:${rtmp_port} 준비 실패 — 로그: ${LOG_DIR}/mediamtx_${rtsp_port}.log"
            return 1
        fi
    done < <(read_streams)
    return 0
}

# --- 송출기 기동 ---------------------------------------------------------------
start_sender() {
    info "RTSP 송출기 기동 (sudo)"
    local log="${LOG_DIR}/rtsp_sender.log"
    # sudo 로 실행하여 tc 조작 권한 확보 + 종료 시 tc 정리 보장
    sudo -v || { err "sudo 권한 필요"; return 1; }
    sudo nohup python3 "$SENDER" -c "$CONFIG" > "$log" 2>&1 &
    echo "$!" > "$SENDER_PIDFILE"
    sleep 2
    if pgrep -f "rtsp_sender.py" >/dev/null 2>&1; then
        ok "송출기 기동됨 (로그: $log)"
        return 0
    else
        err "송출기 기동 실패 — 로그 확인: $log"
        return 1
    fi
}

# --- 통합 기동 -----------------------------------------------------------------
do_start() {
    info "===== 기동 시작 ====="
    # 항상 먼저 정리하여 부분 생존 상태를 제거
    do_stop
    echo
    start_mediamtx || { err "MediaMTX 기동 실패 → 전체 정리"; do_stop; exit 1; }
    echo
    start_sender   || { err "송출기 기동 실패 → 전체 정리"; do_stop; exit 1; }
    echo
    ok "===== 기동 완료 ====="
    do_status
}

# --- 상태 확인 -----------------------------------------------------------------
do_status() {
    echo
    info "===== 상태 ====="
    # MediaMTX
    local mtx_alive=0 mtx_total=0
    while read -r rtsp_port rtmp_port; do
        [[ -z "$rtsp_port" ]] && continue
        mtx_total=$(( mtx_total + 1 ))
        local pf="${RUN_DIR}/mediamtx_${rtsp_port}.pid"
        local pid; pid="$(cat "$pf" 2>/dev/null || true)"
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            ok "  MediaMTX RTSP:${rtsp_port} 실행 중 (PID $pid)"
            mtx_alive=$(( mtx_alive + 1 ))
        else
            warn "  MediaMTX RTSP:${rtsp_port} 중지됨"
        fi
    done < <(read_streams)

    # 송출기
    local sender_alive=0
    if pgrep -f "rtsp_sender.py" >/dev/null 2>&1; then
        ok "  RTSP 송출기 실행 중 (PID: $(pgrep -f 'rtsp_sender.py' | tr '\n' ' '))"
        sender_alive=1
    else
        warn "  RTSP 송출기 중지됨"
    fi

    # 부분 생존 경고
    echo
    if [[ "$mtx_alive" -gt 0 && "$sender_alive" -eq 0 ]]; then
        warn "부분 생존: MediaMTX 만 살아있음 → 'restart' 권장"
    elif [[ "$mtx_alive" -eq 0 && "$sender_alive" -eq 1 ]]; then
        warn "부분 생존: 송출기만 살아있음(서버 없음) → 'restart' 권장"
    elif [[ "$mtx_alive" -eq "$mtx_total" && "$sender_alive" -eq 1 ]]; then
        ok "정상: MediaMTX ${mtx_alive}/${mtx_total} + 송출기 가동 중"
    elif [[ "$mtx_alive" -eq 0 && "$sender_alive" -eq 0 ]]; then
        info "전체 중지 상태"
    else
        warn "일부만 가동: MediaMTX ${mtx_alive}/${mtx_total}, 송출기=${sender_alive} → 'restart' 권장"
    fi
}

# --- 메인 ---------------------------------------------------------------------
main() {
    preflight
    case "${1:-}" in
        start)   do_start ;;
        stop)    do_stop ;;
        restart) do_stop; echo; do_start ;;
        status)  do_status ;;
        *)
            echo "사용법: $0 {start|stop|restart|status}"
            echo
            echo "  start   - MediaMTX → 송출기 순으로 기동 (시작 전 자동 정리)"
            echo "  stop    - 송출기 → MediaMTX 종료 + tc 정리"
            echo "  restart - 완전 종료 후 재기동"
            echo "  status  - 현재 가동 상태 및 부분 생존 감지"
            exit 1
            ;;
    esac
}

main "$@"
