"""RTSP 클라이언트 설정 모듈"""

import os
import logging
from dataclasses import dataclass, field
from typing import Optional, List

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
    save_workers: int = 12
    max_duration_seconds: Optional[int] = None
    frame_loss_rate: float = 0.0
    reconnect_interval: int = 5
    connection_timeout: int = 10
    enable_processing: bool = True
    blur_module_path: Optional[str] = "../../blur_module/ipcamera_blur.py"
    save_enabled: bool = True
    save_path: str = "./output/"
    save_interval: int = 300  # 프레임 단위
    save_format: str = "mp4"
    input_fps: float = 15.0
    force_fps: bool = True
    blur_queue_size: int = 1000
    save_queue_size: int = 1000
    preview_queue_size: int = 50
    processing_queue_size: int = 1000
    
    # 확장된 FFmpeg 설정
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    compression_level: int = 6
    quality_mode: str = "cbr"
    bitrate: str = "4M"
    max_bitrate: str = "4M"
    buffer_size: str = "8M"
    keyframe_interval: int = 250
    pixel_format: str = "yuv420p"
    container_format: str = "mp4"
    ffmpeg_preset: str = "fast"
    ffmpeg_tune: str = "none"
    ffmpeg_profile: str = "main"
    ffmpeg_level: str = "4.1"
    hardware_acceleration: str = "none"
    extra_options: str = ""
    
    # 오버레이 설정
    overlay_enabled: bool = True
    latitude: float = 37.5665
    longitude: float = 126.9780
    
    # 기타 설정
    preview_enabled: bool = True
    blur_enabled: bool = True
    high_performance_mode: bool = False
    
    # 블러 처리 간격 설정
    blur_interval: int = 3  # 몇 프레임마다 블러 처리할지 (1 = 모든 프레임, 2 = 2프레임마다, 3 = 3프레임마다...)

    # 2단계 저장 시스템 설정
    two_stage_storage: bool = False  # 2단계 저장 활성화/비활성화
    ssd_temp_path: str = "./output/temp"  # SSD 임시 저장 경로
    hdd_final_path: str = "/mnt/raid5"  # HDD 최종 저장 경로
    file_move_workers: int = 2  # 파일 이동 워커 수
    file_move_queue_size: int = 100  # 파일 이동 큐 크기
    temp_file_prefix: str = "t_"  # 임시 파일 접두사