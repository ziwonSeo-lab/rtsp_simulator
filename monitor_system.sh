#!/bin/bash

# 시스템 모니터링 스크립트 - RTSP 시뮬레이터 성능 진단용
# 실행: ./monitor_system.sh

echo "=== RTSP 시뮬레이터 시스템 모니터링 ==="
echo "시작 시간: $(date)"
echo ""

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 함수 정의
print_section() {
    echo -e "${BLUE}=== $1 ===${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

# 1. 기본 시스템 정보
print_section "1. 시스템 기본 정보"
echo "호스트명: $(hostname)"
echo "OS: $(lsb_release -d | cut -f2)"
echo "커널: $(uname -r)"
echo "아키텍처: $(uname -m)"
echo "업타임: $(uptime -p)"
echo ""

# 2. CPU 정보
print_section "2. CPU 정보"
echo "CPU 모델: $(lscpu | grep 'Model name' | cut -d':' -f2 | xargs)"
echo "CPU 코어: $(nproc) 코어"
echo "현재 CPU 사용률:"
top -bn1 | grep "Cpu(s)" | head -1
echo ""

# 3. 메모리 상태
print_section "3. 메모리 상태"
free -h
echo ""
echo "메모리 세부 정보:"
cat /proc/meminfo | grep -E "(MemTotal|MemAvailable|Buffers|Cached)" | while read line; do
    echo "  $line"
done
echo ""

# 4. 디스크 공간 및 I/O
print_section "4. 디스크 상태"
echo "디스크 사용량:"
df -h | grep -E "^/dev|Size"
echo ""

echo "현재 디스크 I/O 상태:"
if command -v iostat > /dev/null; then
    iostat -x 1 1 | tail -n +4
else
    print_warning "iostat이 설치되지 않음. 설치: sudo apt install sysstat"
fi
echo ""

# 5. 네트워크 상태
print_section "5. 네트워크 상태"
echo "네트워크 인터페이스:"
ip link show | grep -E "^[0-9]" | awk '{print $2, $9}'
echo ""

echo "현재 네트워크 연결:"
ss -tulpn | grep -E ":111[1-6]" | head -10
echo ""

# 6. RTSP 관련 프로세스 확인
print_section "6. RTSP 관련 프로세스"
echo "Python RTSP 프로세스:"
ps aux | grep -E "(python.*rtsp|rtsp.*python)" | grep -v grep
echo ""

echo "mediamtx 프로세스:"
ps aux | grep mediamtx | grep -v grep
echo ""

# 7. 포트 사용 상태
print_section "7. RTSP 포트 상태"
echo "1111-1116 포트 상태:"
for port in {1111..1116}; do
    if ss -tulpn | grep ":$port " > /dev/null; then
        print_success "포트 $port: 사용 중"
    else
        print_error "포트 $port: 비어있음"
    fi
done
echo ""

# 8. 로그 파일 상태 확인
print_section "8. 로그 파일 상태"
log_files=(
    "./rtsp_processor.log"
    "./code/rtsp_client_module/rtsp_processor.log"
    "./disk_io_test.log"
)

for log_file in "${log_files[@]}"; do
    if [[ -f "$log_file" ]]; then
        size=$(stat -c%s "$log_file")
        size_mb=$((size / 1024 / 1024))
        echo "  $log_file: ${size_mb}MB"
        
        # 최근 에러 확인
        recent_errors=$(tail -100 "$log_file" 2>/dev/null | grep -i -E "(error|fail|exception)" | wc -l)
        if [[ $recent_errors -gt 0 ]]; then
            print_warning "$log_file에서 최근 $recent_errors개 에러 발견"
        fi
    else
        echo "  $log_file: 없음"
    fi
done
echo ""

# 9. 출력 디렉토리 상태
print_section "9. 출력 디렉토리 상태"
output_dirs=(
    "./output"
    "./code/rtsp_client_module/output"
    "./test_output"
)

for dir in "${output_dirs[@]}"; do
    if [[ -d "$dir" ]]; then
        file_count=$(find "$dir" -name "*.mp4" | wc -l)
        total_size=$(du -sh "$dir" 2>/dev/null | cut -f1)
        echo "  $dir: ${file_count}개 파일, 크기: $total_size"
    else
        echo "  $dir: 없음"
    fi
done
echo ""

# 10. 실시간 모니터링 명령어 제안
print_section "10. 실시간 모니터링 명령어"
echo "다음 명령어들을 별도 터미널에서 실행하여 실시간 모니터링하세요:"
echo ""
echo -e "${GREEN}# CPU/메모리/프로세스 모니터링${NC}"
echo "htop"
echo ""
echo -e "${GREEN}# 디스크 I/O 모니터링 (2초마다 업데이트)${NC}"
if command -v iostat > /dev/null; then
    echo "iostat -x 2"
else
    echo "sudo apt install sysstat && iostat -x 2"
fi
echo ""
echo -e "${GREEN}# 프로세스별 I/O 모니터링${NC}"
if command -v iotop > /dev/null; then
    echo "sudo iotop -o -d 2"
else
    echo "sudo apt install iotop && sudo iotop -o -d 2"
fi
echo ""
echo -e "${GREEN}# 네트워크 모니터링${NC}"
echo "watch -n 1 'ss -tulpn | grep -E \":111[1-6]\"'"
echo ""
echo -e "${GREEN}# 로그 실시간 모니터링${NC}"
echo "tail -f ./rtsp_processor.log"
echo ""

# 11. 성능 체크리스트
print_section "11. 성능 체크리스트"
echo "다음 항목들을 확인하세요:"
echo ""

# 메모리 체크
available_mem=$(free -m | awk '/^Mem:/{print $7}')
if [[ $available_mem -lt 1000 ]]; then
    print_error "사용 가능한 메모리: ${available_mem}MB (< 1GB) - 메모리 부족"
else
    print_success "사용 가능한 메모리: ${available_mem}MB"
fi

# CPU 부하 체크
load_avg=$(uptime | awk '{print $(NF-2)}' | sed 's/,//')
cpu_cores=$(nproc)
load_ratio=$(echo "scale=2; $load_avg / $cpu_cores" | bc -l 2>/dev/null || echo "0")
if (( $(echo "$load_ratio > 0.8" | bc -l 2>/dev/null) )); then
    print_error "CPU 부하 높음: $load_avg (코어 당 ${load_ratio})"
else
    print_success "CPU 부하 양호: $load_avg (코어 당 ${load_ratio})"
fi

# 디스크 공간 체크
root_usage=$(df / | awk 'NR==2 {print $5}' | sed 's/%//')
if [[ $root_usage -gt 90 ]]; then
    print_error "루트 디스크 사용률: ${root_usage}% (> 90%)"
else
    print_success "루트 디스크 사용률: ${root_usage}%"
fi

echo ""
echo "=== 모니터링 완료 ==="
echo "종료 시간: $(date)"