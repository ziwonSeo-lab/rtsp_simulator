"""RTSP 클라이언트 설정 모듈"""

import os
import logging
from dataclasses import dataclass, field
from typing import Optional, List
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def get_env_value(key: str, default_value, value_type=str):
    """환경변수에서 값을 가져오는 헬퍼 함수"""
    try:
        value = os.getenv(key)
        if value is None:
            return default_value
        
        if value_type == bool:
            return value.lower() in ('true', '1', 'yes', 'on')
        elif value_type == int:
            return int(value)
        elif value_type == float:
            return float(value)
        else:
            return value
    except (ValueError, TypeError):
        logger.warning(f"환경변수 {key}의 값이 올바르지 않음. 기본값 사용: {default_value}")
        return default_value


@dataclass
class RTSPConfig:
    """RTSP 처리 설정 클래스"""
    sources: List[str] = field(default_factory=lambda: [
        "rtsp://10.2.10.158:1111/live",
        "rtsp://10.2.10.158:1112/live",
        "rtsp://10.2.10.158:1113/live",
        "rtsp://10.2.10.158:1114/live",
        "rtsp://10.2.10.158:1115/live",
        "rtsp://10.2.10.158:1116/live"
    ])
    thread_count: int = get_env_value('DEFAULT_THREAD_COUNT', 6, int)
    blur_workers: int = 3
    save_workers: int = 3  # 12에서 3으로 줄임 (스트림별 15fps 제어가 있으므로)
    max_duration_seconds: Optional[int] = None
    frame_loss_rate: float = 0.0
    reconnect_interval: int = 5
    connection_timeout: int = 10
    enable_processing: bool = True
    blur_module_path: Optional[str] = get_env_value('BLUR_MODULE_PATH', "/home/szw001/development/2025/IUU/rtsp_simulator/blur_module/ipcamera_blur.py")
    save_enabled: bool = True
    save_path: str = "./output/"
    save_interval: int = 300  # 프레임 단위 (20초 × 15fps = 300프레임)
    save_interval_seconds: int = 20  # 시간 기준 파일 분할 (초 단위)
    save_format: str = "mp4"
    input_fps: float = 15.0
    force_fps: bool = True
    blur_queue_size: int = 30      # 버벅임 방지를 위해 큐 크기 축소
    save_queue_size: int = 300      # 저장 지연 최소화
    preview_queue_size: int = 10   # 미리보기 지연 최소화
    processing_queue_size: int = 50 # 전체 처리 지연 최소화
    
    # 확장된 FFmpeg 설정 (화질 최적화)
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    compression_level: int = 18  # CRF 품질 (낮을수록 고화질, 18-23 권장)
    quality_mode: str = "vbr"  # CRF 모드로 변경 (더 나은 화질)
    bitrate: str = "3M"  # 비트레이트 증가
    max_bitrate: str = "6M"  # 최대 비트레이트 증가
    buffer_size: str = "10M"  # 버퍼 크기 증가
    keyframe_interval: int = 30  # 키프레임 간격 단축 (더 안정적)
    pixel_format: str = "yuv420p"
    container_format: str = "mp4"
    ffmpeg_preset: str = "medium"  # 화질 우선 (slow > medium > fast)
    ffmpeg_tune: str = "film"  # 실사 영상에 최적화
    ffmpeg_profile: str = "high"  # High 프로파일 (더 나은 압축)
    ffmpeg_level: str = "4.1"
    hardware_acceleration: str = "none"
    extra_options: str = "-movflags +faststart"  # 웹 재생 최적화
    
    # 오버레이 설정
    overlay_enabled: bool = True
    latitude: str = "N 37d33'59.4\""
    longitude: str = "E 126d58'40.8\""
    
    # 기타 설정
    preview_enabled: bool = True
    blur_enabled: bool = False  # 블러 처리 비활성화 (버벅임 문제 해결을 위해)
    high_performance_mode: bool = False
    
    # 저장 옵션 설정
    save_original_video: bool = True   # 원본 영상 저장 (수신 영상)
    save_blurred_video: bool = True    # 블러 처리된 영상 저장
    
    # 블러 처리 간격 설정
    blur_interval: int = 3  # 몇 프레임마다 블러 처리할지 (1 = 모든 프레임, 2 = 2프레임마다, 3 = 3프레임마다...)

    # 2단계 저장 시스템 설정
    two_stage_storage: bool = True  # 2단계 저장 활성화/비활성화 (기본값: True로 변경)
    ssd_temp_path: str = "./output/temp"  # SSD 임시 저장 경로
    hdd_final_path: str = "./output/final"  # HDD 최종 저장 경로 (더 안전한 경로로 변경)
    file_move_workers: int = 2  # 파일 이동 워커 수
    file_move_queue_size: int = 100  # 파일 이동 큐 크기
    temp_file_prefix: str = "t_"  # 임시 파일 접두사

    ship_name: str = "testShip"

if __name__ == "__main__":
    print(get_env_value("BLUR_MODULE_PATH", None))
    