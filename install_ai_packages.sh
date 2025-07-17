#!/bin/bash
# RTSP 시뮬레이터 v2 - AI 패키지 설치 스크립트
# CUDA 12.1 + TensorRT 10.0 + PyTorch 2.5.1 설치

set -e  # 오류 발생 시 스크립트 중단

echo "🚀 RTSP 시뮬레이터 v2 - AI 패키지 설치 시작"
echo "===================================================="

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 함수 정의
print_step() {
    echo -e "${BLUE}[단계 $1]${NC} $2"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# GPU 확인
print_step "0" "GPU 및 CUDA 환경 확인"
if command -v nvidia-smi &> /dev/null; then
    echo "NVIDIA GPU 정보:"
    nvidia-smi --query-gpu=name,memory.total,driver_version,cuda_version --format=csv,noheader,nounits
    print_success "NVIDIA GPU 감지됨"
else
    print_warning "nvidia-smi를 찾을 수 없습니다. NVIDIA 드라이버를 확인하세요."
fi

# 가상환경 확인
if [[ "$VIRTUAL_ENV" != "" ]]; then
    print_success "가상환경 활성화됨: $VIRTUAL_ENV"
else
    print_warning "가상환경이 활성화되지 않았습니다. 계속하려면 y를 입력하세요."
    read -p "계속하시겠습니까? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_error "설치가 취소되었습니다."
        exit 1
    fi
fi

# 1. 기본 패키지 설치
print_step "1" "기본 패키지 설치"
pip install --upgrade pip setuptools wheel
pip install opencv-python pillow numpy psutil GPUtil
print_success "기본 패키지 설치 완료"

# 2. PyTorch 2.5.1 + CUDA 12.1 설치
print_step "2" "PyTorch 2.5.1 + CUDA 12.1 설치"
pip install torch==2.5.1+cu121 torchvision==0.20.1+cu121 \
            --index-url https://download.pytorch.org/whl/cu121
print_success "PyTorch CUDA 12.1 설치 완료"

# 3. 시스템 의존성 설치 (cmake)
print_step "3" "시스템 의존성 설치 (cmake)"
if command -v cmake &> /dev/null; then
    print_success "cmake가 이미 설치되어 있습니다."
else
    echo "cmake 설치 중... (sudo 권한 필요)"
    sudo apt-get update -qq
    sudo apt-get install -y cmake
    print_success "cmake 설치 완료"
fi

# 4. ONNX 관련 패키지 설치
print_step "4" "ONNX 관련 패키지 설치"
pip install onnxsim==0.4.33 onnxruntime-gpu
print_success "ONNX 패키지 설치 완료"

# 5. TensorRT 설치 (NVIDIA PyPI 레지스트리)
print_step "5" "TensorRT 10.0.1 설치"
pip install tensorrt-cu12==10.0.1 \
            tensorrt-cu12-bindings==10.0.1 \
            tensorrt-cu12-libs==10.0.1 \
            --extra-index-url https://pypi.ngc.nvidia.com
print_success "TensorRT 설치 완료"

# 6. Ultralytics YOLO 최신 버전 설치
print_step "6" "Ultralytics YOLO 최신 버전 설치"
pip install --upgrade ultralytics
print_success "Ultralytics YOLO 설치 완료"

# 7. 추가 AI/ML 패키지 설치
print_step "7" "추가 AI/ML 패키지 설치"
pip install scikit-image matplotlib
print_success "추가 패키지 설치 완료"

# 8. 설치 확인 및 테스트
print_step "8" "설치 확인 및 테스트"

echo "🔍 설치된 패키지 버전 확인:"
echo "----------------------------------------"

# PyTorch 확인
python -c "import torch; print(f'PyTorch: {torch.__version__}')" 2>/dev/null || print_error "PyTorch 임포트 실패"
python -c "import torch; print(f'CUDA 사용 가능: {torch.cuda.is_available()}')" 2>/dev/null || print_error "CUDA 확인 실패"

# TensorRT 확인  
python -c "import tensorrt; print(f'TensorRT: {tensorrt.__version__}')" 2>/dev/null || print_error "TensorRT 임포트 실패"

# ONNX 확인
python -c "import onnx; print(f'ONNX: {onnx.__version__}')" 2>/dev/null || print_error "ONNX 임포트 실패"
python -c "import onnxruntime; print(f'ONNX Runtime: {onnxruntime.__version__}')" 2>/dev/null || print_error "ONNX Runtime 임포트 실패"

# Ultralytics 확인
python -c "import ultralytics; print(f'Ultralytics: {ultralytics.__version__}')" 2>/dev/null || print_error "Ultralytics 임포트 실패"

# GPU 모니터링 확인
python -c "import GPUtil; gpus = GPUtil.getGPUs(); print(f'GPU 모니터링: {len(gpus)}개 GPU 감지')" 2>/dev/null || print_error "GPUtil 확인 실패"

echo "----------------------------------------"

# 9. YOLO 모델 다운로드 테스트 (선택적)
echo
read -p "🤖 YOLO 모델 다운로드 테스트를 수행하시겠습니까? (Y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$|^$ ]]; then
    print_step "9" "YOLO 모델 다운로드 테스트"
    python -c "
from ultralytics import YOLO
print('YOLOv8n 모델 다운로드 중...')
model = YOLO('yolov8n.pt')
print('✅ YOLO 모델 다운로드 및 로드 성공')
print(f'모델 정보: {model.info()}')
" 2>/dev/null && print_success "YOLO 모델 테스트 완료" || print_warning "YOLO 모델 테스트 실패 (인터넷 연결 확인)"
fi

# 완료 메시지
echo
echo "===================================================="
print_success "🎉 AI 패키지 설치가 완료되었습니다!"
echo
echo "📋 설치된 주요 패키지:"
echo "  • PyTorch 2.5.1 + CUDA 12.1"
echo "  • TensorRT 10.0.1"
echo "  • ONNX Runtime GPU"
echo "  • Ultralytics YOLO (최신)"
echo "  • GPUtil (GPU 모니터링)"
echo
echo "🚀 이제 rtsp_simulator_ffmpeg_v2.py를 실행할 수 있습니다:"
echo "   python rtsp_simulator_ffmpeg_v2.py"
echo
echo "📊 GPU 상태 확인:"
nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu --format=csv,noheader,nounits 2>/dev/null || echo "nvidia-smi 사용 불가"
echo "====================================================" 