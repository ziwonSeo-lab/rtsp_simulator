"""
RTSP 클라이언트 모듈

multi-process_rtsp.py에서 추출된 모듈화된 RTSP 클라이언트 시스템

주요 구성요소:
- config: RTSP 설정 및 환경변수 관리
- statistics: 프레임 통계 및 시스템 리소스 모니터링
- video_writer: FFmpeg 기반 비디오 라이터
- workers: 멀티프로세스 워커 함수들
- processor: RTSP 처리 메인 프로세서
- gui: 기본 GUI 인터페이스
"""

from .config import RTSPConfig, get_env_value
from .statistics import (
    FrameStatistics, 
    FrameCounter, 
    ResourceMonitor, 
    PerformanceProfiler
)
from .video_writer import EnhancedFFmpegVideoWriter
from .workers import (
    rtsp_capture_process,
    blur_worker_process, 
    save_worker_process
)
from .processor import SharedPoolRTSPProcessor
from .gui import RTSPProcessorGUI, create_gui

__version__ = "1.0.0"
__author__ = "RTSP Simulator Team"

__all__ = [
    # Config
    'RTSPConfig',
    'get_env_value',
    
    # Statistics
    'FrameStatistics',
    'FrameCounter', 
    'ResourceMonitor',
    'PerformanceProfiler',
    
    # Video Writer
    'EnhancedFFmpegVideoWriter',
    
    # Workers
    'rtsp_capture_process',
    'blur_worker_process',
    'save_worker_process',
    
    # Processor
    'SharedPoolRTSPProcessor',
    
    # GUI
    'RTSPProcessorGUI',
    'create_gui'
]