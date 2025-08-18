"""
설정 관리 모듈

환경변수 로드 및 단일 스트림 처리를 위한 설정 클래스들
"""

import os
import re
from dataclasses import dataclass
from typing import Optional, Tuple, Dict, List, Any
from datetime import datetime
import logging

try:
    from dotenv import load_dotenv
    load_dotenv()
    ENV_LOADED = True
except ImportError:
    ENV_LOADED = False

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
class OverlayConfig:
    """오버레이 표시 정보 (60분법 GPS)"""
    vessel_name: str = "DEFAULT_VESSEL"
    stream_number: int = 1
    latitude: float = 37.5665            # 십진법으로 저장 (서울 기본값)
    longitude: float = 126.9780          # 십진법으로 저장 (서울 기본값) 
    use_server_time: bool = True
    
    # TODO: Redis 연동 시 실시간 데이터 수신
    # def update_from_redis(self, redis_data: Dict):
    #     self.vessel_name = redis_data.get('vessel_name', self.vessel_name)
    #     self.latitude = redis_data.get('latitude', self.latitude)
    #     self.longitude = redis_data.get('longitude', self.longitude)

@dataclass
class FFmpegConfig:
    """15fps VBR 최적화 FFmpeg 설정"""
    
    # 기본 코덱 및 비트레이트 설정 (환경변수로 덮어쓰기 가능)
    video_codec: str = get_env_value('FFMPEG_VIDEO_CODEC', "libx264")
    compression_level: int = get_env_value('FFMPEG_COMPRESSION_LEVEL', 6, int)
    quality_mode: str = get_env_value('FFMPEG_QUALITY_MODE', "vbr")      # vbr/cbr
    target_bitrate: str = get_env_value('FFMPEG_TARGET_BITRATE', "2M")
    min_bitrate: str = get_env_value('FFMPEG_MIN_BITRATE', "1M")
    max_bitrate: str = get_env_value('FFMPEG_MAX_BITRATE', "4M")
    
    # FPS / GOP
    input_fps: float = get_env_value('FFMPEG_INPUT_FPS', 15.0, float)
    output_fps: float = get_env_value('FFMPEG_OUTPUT_FPS', 15.0, float)
    keyframe_interval: int = get_env_value('FFMPEG_KEYINT', 45, int)  # 3초 @15fps
    
    # 컨테이너/픽셀 포맷
    container_format: str = get_env_value('FFMPEG_CONTAINER', "mp4")
    pixel_format: str = get_env_value('FFMPEG_PIXEL_FORMAT', "yuv420p")
    
    # 성능 설정
    preset: str = get_env_value('FFMPEG_PRESET', "medium")
    tune: str = get_env_value('FFMPEG_TUNE', "film")
    profile: str = get_env_value('FFMPEG_PROFILE', "main")
    level: str = get_env_value('FFMPEG_LEVEL', "4.1")
    
    # 버퍼/동기화/로그
    buffer_size: str = get_env_value('FFMPEG_BUFFER_SIZE', "4M")
    vsync_mode: str = get_env_value('FFMPEG_VSYNC', 'cfr')  # cfr/vfr/drop
    loglevel: str = get_env_value('FFMPEG_LOGLEVEL', 'error')
    
    # 하드웨어 가속
    hardware_acceleration: str = get_env_value('FFMPEG_HWACCEL', "none")  # none,nvidia,intel,amd
    
    def get_ffmpeg_command(self, input_settings: Dict, output_file: str) -> List[str]:
        """15fps VBR 최적화 FFmpeg 명령어 생성"""
        cmd = ['ffmpeg', '-y', '-hide_banner', '-loglevel', self.loglevel]
        
        # 하드웨어 가속 (필요시) - 입력이 rawvideo라 디코드 가속은 영향이 적지만, 향후 확장 고려
        if self.hardware_acceleration == "nvidia":
            cmd.extend(['-hwaccel', 'cuda'])
        elif self.hardware_acceleration == "intel":
            cmd.extend(['-hwaccel', 'qsv'])
        
        # 입력 설정
        cmd.extend([
            '-f', 'rawvideo',
            '-vcodec', 'rawvideo',
            '-s', f"{input_settings['width']}x{input_settings['height']}",
            '-pix_fmt', 'bgr24',
            '-r', str(int(self.input_fps)),  # 입력 fps
            '-i', '-'
        ])
        
        # 비디오 코덱 설정
        cmd.extend(['-c:v', self.video_codec])
        
        # VBR/CBR 품질 설정
        cmd.extend([
            '-b:v', self.target_bitrate,
            '-minrate', self.min_bitrate,
            '-maxrate', self.max_bitrate,
            '-bufsize', self.buffer_size
        ])
        
        # 출력 fps 및 품질
        cmd.extend([
            '-r', str(int(self.output_fps)),
            '-preset', self.preset,
            '-tune', self.tune,
            '-profile:v', self.profile,
            '-level', self.level,
            '-g', str(self.keyframe_interval),
            '-pix_fmt', self.pixel_format
        ])
        
        # 공통 최적화
        cmd.extend([
            '-threads', '0',
            '-movflags', '+faststart',
            '-avoid_negative_ts', 'make_zero',
            '-vsync', self.vsync_mode
        ])
        
        cmd.append(output_file)
        return cmd

@dataclass
class RTSPConfig:
    """단일 스트림 처리를 위한 설정 클래스"""
    
    # 기본 설정
    rtsp_url: str                                        # 단일 RTSP URL
    temp_output_path: str = get_env_value('TEMP_OUTPUT_PATH', "./output/temp/")
    final_output_path: str = get_env_value('FINAL_OUTPUT_PATH', "/mnt/raid5")
    max_duration_seconds: Optional[int] = get_env_value('DEFAULT_MAX_DURATION', None, int)
    
    # 영상 처리 설정
    input_fps: float = 15.0                              # 입력 FPS (고정)
    target_resolution: Tuple[int, int] = (1920, 1080)   # 목표 해상도
    
    # 블러 처리 설정
    blur_module_path: Optional[str] = get_env_value('BLUR_MODULE_PATH', None)
    blur_enabled: bool = True                            # 블러 처리 활성화
    blur_confidence: float = 0.5                         # YOLO 신뢰도 임계값
    
    # 큐 설정 (스레드간 통신)
    frame_queue_size: int = 100                          # 프레임 큐 크기
    
    # 연결 설정
    connection_timeout: int = 10                         # 연결 타임아웃
    reconnect_interval: int = 5                          # 재연결 간격
    
    # 모니터링 설정
    enable_monitoring: bool = True                       # 리소스 모니터링 활성화
    monitoring_interval: float = 1.0                     # 모니터링 주기 (초)
    
    # API 설정
    blackbox_enabled: bool = True                      # 블랙박스 API 사용 여부
    blackbox_api_url: str = get_env_value('BLACKBOX_API_URL', 'http://localhost')
    api_timeout: int = get_env_value('API_TIMEOUT', 5, int)
    api_poll_interval: float = get_env_value('API_POLL_INTERVAL', 1.0, float)
    
    # 녹화 조건 설정
    recording_speed_threshold: float = get_env_value('RECORDING_SPEED_THRESHOLD', 5, float)
    
    # 오버레이 설정
    overlay_config: OverlayConfig = None
    
    # FFmpeg 설정
    ffmpeg_config: FFmpegConfig = None
    
    def __post_init__(self):
        """초기화 후 처리"""
        if self.overlay_config is None:
            self.overlay_config = OverlayConfig(
                vessel_name=get_env_value('VESSEL_NAME', 'DEFAULT_VESSEL'),
                stream_number=get_env_value('STREAM_NUMBER', 1, int),
                latitude=get_env_value('DEFAULT_LATITUDE', 37.5665, float),
                longitude=get_env_value('DEFAULT_LONGITUDE', 126.9780, float)
            )
        
        if self.ffmpeg_config is None:
            self.ffmpeg_config = FFmpegConfig()
        
        # 임시 출력 경로 생성
        os.makedirs(self.temp_output_path, exist_ok=True)
    
    @classmethod
    def from_env(cls, rtsp_url: str = None) -> 'RTSPConfig':
        """환경변수에서 설정 로드"""
        if rtsp_url is None:
            rtsp_url = get_env_value('RTSP_URL', 'rtsp://localhost:8554/stream')
        
        # 해상도 환경변수 처리
        width = get_env_value('VIDEO_WIDTH', 1920, int)
        height = get_env_value('VIDEO_HEIGHT', 1080, int)
        
        return cls(
            rtsp_url=rtsp_url,
            temp_output_path=get_env_value('TEMP_OUTPUT_PATH', "./output/temp/"),
            final_output_path=get_env_value('FINAL_OUTPUT_PATH', "/mnt/raid5"),
            max_duration_seconds=get_env_value('DEFAULT_MAX_DURATION', None, int),
            input_fps=get_env_value('DEFAULT_INPUT_FPS', 15.0, float),
            target_resolution=(width, height),
            blur_module_path=get_env_value('BLUR_MODULE_PATH', None),
            blur_enabled=get_env_value('BLUR_ENABLED', True, bool),
            frame_queue_size=get_env_value('FRAME_QUEUE_SIZE', 100, int),
            connection_timeout=get_env_value('CONNECTION_TIMEOUT', 10, int),
            reconnect_interval=get_env_value('RECONNECT_INTERVAL', 5, int),
            enable_monitoring=get_env_value('ENABLE_MONITORING', True, bool),
            monitoring_interval=get_env_value('MONITORING_INTERVAL', 1.0, float),
            blackbox_enabled=get_env_value('BLACKBOX_ENABLED', True, bool),
            blackbox_api_url=get_env_value('BLACKBOX_API_URL', 'http://localhost'),
            api_timeout=get_env_value('API_TIMEOUT', 5, int),
            api_poll_interval=get_env_value('API_POLL_INTERVAL', 1.0, float),
            recording_speed_threshold=get_env_value('RECORDING_SPEED_THRESHOLD', 5.0, float)
        )
    
    def validate(self) -> bool:
        """설정 검증"""
        try:
            # RTSP URL 기본 검증
            if not self.rtsp_url or not isinstance(self.rtsp_url, str):
                logger.error("RTSP URL이 설정되지 않았습니다.")
                return False
            
            # 출력 경로 검증
            if not os.path.exists(os.path.dirname(self.temp_output_path)):
                logger.error(f"임시 출력 경로가 존재하지 않습니다: {self.temp_output_path}")
                return False
            
            # FPS 검증
            if self.input_fps <= 0:
                logger.error("FPS는 0보다 커야 합니다.")
                return False
            
            # 큐 크기 검증
            if self.frame_queue_size <= 0:
                logger.error("프레임 큐 크기는 0보다 커야 합니다.")
                return False
            
            logger.info("설정 검증 완료")
            return True
            
        except Exception as e:
            logger.error(f"설정 검증 중 오류: {e}")
            return False

def generate_filename(overlay_config: OverlayConfig, timestamp: datetime = None) -> str:
    """파일명 생성: {배이름}_{스트림번호}_{YYMMDD}_{HHMMSS}.mp4"""
    if timestamp is None:
        timestamp = datetime.now()
    
    date_str = timestamp.strftime("%y%m%d")    # YYMMDD
    time_str = timestamp.strftime("%H%M%S")    # HHMMSS
    
    # 배 이름에서 특수문자 제거 (파일명 안전성)
    safe_vessel_name = re.sub(r'[^\w\-_]', '_', overlay_config.vessel_name)
    
    filename = f"{safe_vessel_name}_stream{overlay_config.stream_number:02d}_{date_str}_{time_str}.mp4"
    return filename

def decimal_to_dms_short(decimal_degrees: float, is_longitude: bool = False) -> str:
    """짧은 형식의 60분법 변환 (소수점 1자리)"""
    direction = ("E" if decimal_degrees >= 0 else "W") if is_longitude else ("N" if decimal_degrees >= 0 else "S")
    abs_degrees = abs(decimal_degrees)
    degrees = int(abs_degrees)
    minutes_float = (abs_degrees - degrees) * 60
    minutes = int(minutes_float)
    seconds = (minutes_float - minutes) * 60
    
    # 컴팩트 형식: 123°45'12.3"E
    return f"{degrees:03d}d{minutes:02d}'{seconds:04.1f}\"{direction}"

def format_gps_coordinates(latitude: float, longitude: float) -> tuple[str, str]:
    """GPS 좌표를 60분법으로 포맷팅"""
    lat_dms = decimal_to_dms_short(latitude, is_longitude=False)
    lon_dms = decimal_to_dms_short(longitude, is_longitude=True)
    return lat_dms, lon_dms 