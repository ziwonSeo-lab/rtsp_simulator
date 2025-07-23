"""
RTSP Simulator with Thread-specific YOLO Instances (v2)

🆕 주요 변경사항:
- 스레드별로 독립적인 YOLO/HeadBlurrer 인스턴스 생성
- GPU 모델 경합 해결을 위한 스레드 격리
- 성능 향상 및 안정성 개선

📋 변경 내용:
1. blur_module → blur_modules (딕셔너리로 변경)
2. load_blur_module_for_thread() 메서드 추가
3. 각 스레드 시작 시 개별 blur 모듈 인스턴스 로드
4. process_frame에서 스레드별 모듈 사용
5. 종료 시 모든 스레드별 모듈 정리
"""

import cv2
import threading
import time
import queue
import logging
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
import random
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk
import numpy as np
import os
import importlib.util
import subprocess
import shutil
import psutil
import dotenv

try:
    import GPUtil
    GPU_AVAILABLE = True
except ImportError:
    GPU_AVAILABLE = False
    GPUtil = None
from collections import deque
import json
from datetime import datetime


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 환경변수 관리
try:
    from dotenv import load_dotenv
    load_dotenv()  # .env 파일 로드
    ENV_LOADED = True
except ImportError:
    ENV_LOADED = False
    logger.warning("python-dotenv가 설치되지 않음. 환경변수 파일(.env)을 사용할 수 없습니다.")

# 로깅 설정

# 환경변수 헬퍼 함수
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
    sources: List[str]  # 소스 리스트 (RTSP URL 또는 파일 경로)
    thread_count: int = get_env_value('DEFAULT_THREAD_COUNT', 6, int)
    max_duration_seconds: Optional[int] = get_env_value('DEFAULT_MAX_DURATION', None, int)
    frame_loss_rate: float = 0.0
    reconnect_interval: int = 5
    connection_timeout: int = 10
    enable_processing: bool = True
    blur_module_path: Optional[str] = get_env_value('BLUR_MODULE_PATH', None)  # 블러 모듈 경로
    save_enabled: bool = False  # 저장 활성화
    save_path: str = get_env_value('DEFAULT_OUTPUT_PATH', "./output/")  # 저장 경로
    save_interval: int = 1  # 저장 간격 (1=모든 프레임)
    save_format: str = "jpg"  # 저장 포맷
    input_fps: float = get_env_value('DEFAULT_INPUT_FPS', 15.0, float)  # 입력 영상 FPS
    force_fps: bool = True  # FPS 강제 설정 여부
    processing_queue_size: int = 1000  # 처리 큐 크기
    preview_queue_size: int = 50  # 미리보기 큐 크기
    # 확장된 FFmpeg 설정
    video_codec: str = "libx264"  # 비디오 코덱
    audio_codec: str = "aac"  # 오디오 코덱
    compression_level: int = 6  # 압축 레벨 (0-9)
    quality_mode: str = "cbr"  # 품질 모드 (crf, cbr, vbr)
    bitrate: str = "2M"  # 비트레이트
    max_bitrate: str = "4M"  # 최대 비트레이트
    buffer_size: str = "8M"  # 버퍼 크기
    keyframe_interval: int = 250  # 키프레임 간격
    pixel_format: str = "yuv420p"  # 픽셀 포맷
    container_format: str = "mp4"  # 컨테이너 포맷
    ffmpeg_preset: str = "fast"  # 인코딩 프리셋
    ffmpeg_tune: str = "none"  # 튜닝 옵션
    ffmpeg_profile: str = "main"  # 프로파일
    ffmpeg_level: str = "4.1"  # 레벨
    hardware_acceleration: str = "none"  # 하드웨어 가속
    extra_options: str = ""  # 추가 옵션
    # 오버레이 설정
    overlay_enabled: bool = True  # 오버레이 활성화
    latitude: float = 37.5665  # 위도 (서울 기본값)
    longitude: float = 126.9780  # 경도 (서울 기본값)
    # 미리보기 설정
    preview_enabled: bool = True  # 실시간 미리보기 활성화
    # 블러 설정
    blur_enabled: bool = True  # 블러 처리 활성화
    # 고성능 모드 설정
    high_performance_mode: bool = False  # 고성능 모드 (모든 오버헤드 제거)

class FrameCounter:
    """프레임 카운터 클래스"""
    def __init__(self):
        self.received_frames = 0
        self.processed_frames = 0
        self.saved_frames = 0
        self.lost_frames = 0
        self.error_frames = 0
        self.total_frames = 0
        self.lock = threading.Lock()
    
    def increment_received(self):
        with self.lock:
            self.received_frames += 1
            self.total_frames += 1
    
    def increment_processed(self):
        with self.lock:
            self.processed_frames += 1
    
    def increment_saved(self):
        with self.lock:
            self.saved_frames += 1
    
    def increment_lost(self):
        with self.lock:
            self.lost_frames += 1
    
    def increment_error(self):
        with self.lock:
            self.error_frames += 1
    
    def get_stats(self):
        with self.lock:
            return {
                'received_frames': self.received_frames,
                'processed_frames': self.processed_frames,
                'saved_frames': self.saved_frames,
                'lost_frames': self.lost_frames,
                'error_frames': self.error_frames,
                'total_frames': self.total_frames,
                'loss_rate': self.lost_frames / max(self.total_frames, 1) * 100,
                'processing_rate': self.processed_frames / max(self.total_frames, 1) * 100,
                'save_rate': self.saved_frames / max(self.processed_frames, 1) * 100
            }
    
    def reset(self):
        with self.lock:
            self.received_frames = 0
            self.processed_frames = 0
            self.saved_frames = 0
            self.lost_frames = 0
            self.error_frames = 0
            self.total_frames = 0

class ResourceMonitor:
    """시스템 리소스 모니터링 클래스"""
    
    def __init__(self, history_size: int = 60):
        self.history_size = history_size
        self.cpu_history = deque(maxlen=history_size)
        self.ram_history = deque(maxlen=history_size)
        self.gpu_history = deque(maxlen=history_size)
        self.process = psutil.Process()
        self.lock = threading.Lock()
        self.monitoring = False
        self.monitor_thread = None
        
        # GPU 정보 초기화
        self.gpu_available = GPU_AVAILABLE
        if self.gpu_available:
            try:
                self.gpus = GPUtil.getGPUs()
                if not self.gpus:
                    self.gpu_available = False
            except Exception as e:
                logger.warning(f"GPU 초기화 실패: {e}")
                self.gpu_available = False
    
    def start_monitoring(self):
        """모니터링 시작"""
        if not self.monitoring:
            self.monitoring = True
            self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self.monitor_thread.start()
            logger.info("리소스 모니터링 시작됨")
    
    def stop_monitoring(self):
        """모니터링 중지"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
        logger.info("리소스 모니터링 중지됨")
    
    def _monitor_loop(self):
        """모니터링 루프"""
        while self.monitoring:
            try:
                # CPU 사용률
                cpu_percent = self.process.cpu_percent()
                cpu_system = psutil.cpu_percent()
                
                # RAM 사용량
                memory_info = self.process.memory_info()
                memory_percent = self.process.memory_percent()
                system_memory = psutil.virtual_memory()
                
                # GPU 사용률
                gpu_info = self._get_gpu_info()
                
                with self.lock:
                    self.cpu_history.append({
                        'timestamp': time.time(),
                        'process_cpu': cpu_percent,
                        'system_cpu': cpu_system,
                        'cpu_count': psutil.cpu_count()
                    })
                    
                    self.ram_history.append({
                        'timestamp': time.time(),
                        'process_ram_mb': memory_info.rss / 1024 / 1024,
                        'process_ram_percent': memory_percent,
                        'system_ram_used_gb': system_memory.used / 1024 / 1024 / 1024,
                        'system_ram_total_gb': system_memory.total / 1024 / 1024 / 1024,
                        'system_ram_percent': system_memory.percent
                    })
                    
                    if gpu_info:
                        self.gpu_history.append(gpu_info)
                
                time.sleep(1)  # 1초마다 모니터링
                
            except Exception as e:
                logger.error(f"리소스 모니터링 오류: {e}")
                time.sleep(1)
    
    def _get_gpu_info(self) -> Optional[Dict[str, Any]]:
        """GPU 정보 가져오기"""
        if not self.gpu_available:
            return None
        
        try:
            gpus = GPUtil.getGPUs()
            if not gpus:
                return None
            
            gpu_data = {
                'timestamp': time.time(),
                'gpus': []
            }
            
            for i, gpu in enumerate(gpus):
                gpu_data['gpus'].append({
                    'id': i,
                    'name': gpu.name,
                    'load': gpu.load * 100,  # 사용률 (%)
                    'memory_used_mb': gpu.memoryUsed,
                    'memory_total_mb': gpu.memoryTotal,
                    'memory_percent': (gpu.memoryUsed / gpu.memoryTotal) * 100 if gpu.memoryTotal > 0 else 0,
                    'temperature': gpu.temperature
                })
            
            return gpu_data
            
        except Exception as e:
            logger.warning(f"GPU 정보 가져오기 실패: {e}")
            return None
    
    def get_current_stats(self) -> Dict[str, Any]:
        """현재 리소스 사용량 반환"""
        with self.lock:
            stats = {
                'cpu': self.cpu_history[-1] if self.cpu_history else None,
                'ram': self.ram_history[-1] if self.ram_history else None,
                'gpu': self.gpu_history[-1] if self.gpu_history else None,
                'gpu_available': self.gpu_available
            }
        return stats
    
    def get_history(self) -> Dict[str, Any]:
        """전체 히스토리 반환"""
        with self.lock:
            return {
                'cpu_history': list(self.cpu_history),
                'ram_history': list(self.ram_history),
                'gpu_history': list(self.gpu_history),
                'gpu_available': self.gpu_available
            }
    
    def get_summary_stats(self) -> Dict[str, Any]:
        """요약 통계 반환"""
        with self.lock:
            if not self.cpu_history:
                return {}
            
            # CPU 통계
            cpu_process = [entry['process_cpu'] for entry in self.cpu_history]
            cpu_system = [entry['system_cpu'] for entry in self.cpu_history]
            
            # RAM 통계
            ram_process = [entry['process_ram_mb'] for entry in self.ram_history]
            ram_system = [entry['system_ram_percent'] for entry in self.ram_history]
            
            stats = {
                'cpu': {
                    'process_avg': sum(cpu_process) / len(cpu_process),
                    'process_max': max(cpu_process),
                    'system_avg': sum(cpu_system) / len(cpu_system),
                    'system_max': max(cpu_system)
                },
                'ram': {
                    'process_avg_mb': sum(ram_process) / len(ram_process),
                    'process_max_mb': max(ram_process),
                    'system_avg_percent': sum(ram_system) / len(ram_system),
                    'system_max_percent': max(ram_system)
                }
            }
            
            # GPU 통계
            if self.gpu_history and self.gpu_available:
                gpu_loads = []
                gpu_memory = []
                
                for entry in self.gpu_history:
                    for gpu in entry['gpus']:
                        gpu_loads.append(gpu['load'])
                        gpu_memory.append(gpu['memory_percent'])
                
                if gpu_loads:
                    stats['gpu'] = {
                        'load_avg': sum(gpu_loads) / len(gpu_loads),
                        'load_max': max(gpu_loads),
                        'memory_avg_percent': sum(gpu_memory) / len(gpu_memory),
                        'memory_max_percent': max(gpu_memory)
                    }
            
            return stats

class PerformanceProfiler:
    """성능 프로파일링 클래스"""
    
    def __init__(self):
        self.profiles = {}
        self.thread_profiles = {}
        self.lock = threading.Lock()
        
    def start_profile(self, name: str, thread_id: Optional[int] = None):
        """프로파일링 시작"""
        profile_key = f"{name}_{thread_id}" if thread_id is not None else name
        
        with self.lock:
            if thread_id is not None:
                if thread_id not in self.thread_profiles:
                    self.thread_profiles[thread_id] = {}
                self.thread_profiles[thread_id][name] = {
                    'start_time': time.time(),
                    'end_time': None,
                    'duration': None
                }
            else:
                self.profiles[name] = {
                    'start_time': time.time(),
                    'end_time': None,
                    'duration': None
                }
    
    def end_profile(self, name: str, thread_id: Optional[int] = None):
        """프로파일링 종료"""
        end_time = time.time()
        
        with self.lock:
            if thread_id is not None:
                if thread_id in self.thread_profiles and name in self.thread_profiles[thread_id]:
                    profile = self.thread_profiles[thread_id][name]
                    profile['end_time'] = end_time
                    profile['duration'] = end_time - profile['start_time']
            else:
                if name in self.profiles:
                    profile = self.profiles[name]
                    profile['end_time'] = end_time
                    profile['duration'] = end_time - profile['start_time']
    
    def get_profile_stats(self) -> Dict[str, Any]:
        """프로파일 통계 반환"""
        with self.lock:
            stats = {
                'global_profiles': {},
                'thread_profiles': {},
                'summary': {}
            }
            
            # 전역 프로파일
            for name, profile in self.profiles.items():
                if profile['duration'] is not None:
                    stats['global_profiles'][name] = {
                        'duration_ms': profile['duration'] * 1000,
                        'start_time': profile['start_time'],
                        'end_time': profile['end_time']
                    }
            
            # 쓰레드별 프로파일
            for thread_id, thread_profiles in self.thread_profiles.items():
                stats['thread_profiles'][thread_id] = {}
                
                for name, profile in thread_profiles.items():
                    if profile['duration'] is not None:
                        stats['thread_profiles'][thread_id][name] = {
                            'duration_ms': profile['duration'] * 1000,
                            'start_time': profile['start_time'],
                            'end_time': profile['end_time']
                        }
            
            # 요약 통계
            all_durations = {}
            
            # 전역 프로파일에서 수집
            for name, profile in self.profiles.items():
                if profile['duration'] is not None:
                    if name not in all_durations:
                        all_durations[name] = []
                    all_durations[name].append(profile['duration'])
            
            # 쓰레드별 프로파일에서 수집
            for thread_profiles in self.thread_profiles.values():
                for name, profile in thread_profiles.items():
                    if profile['duration'] is not None:
                        if name not in all_durations:
                            all_durations[name] = []
                        all_durations[name].append(profile['duration'])
            
            # 요약 통계 계산
            for name, durations in all_durations.items():
                if durations:
                    stats['summary'][name] = {
                        'count': len(durations),
                        'avg_ms': (sum(durations) / len(durations)) * 1000,
                        'min_ms': min(durations) * 1000,
                        'max_ms': max(durations) * 1000,
                        'total_ms': sum(durations) * 1000
                    }
            
            return stats
    
    def reset(self):
        """프로파일 데이터 초기화"""
        with self.lock:
            self.profiles.clear()
            self.thread_profiles.clear()
    
    def save_to_file(self, filepath: str):
        """프로파일 데이터를 파일로 저장"""
        try:
            stats = self.get_profile_stats()
            stats['saved_at'] = datetime.now().isoformat()
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(stats, f, indent=2, ensure_ascii=False)
            
            logger.info(f"성능 프로파일 저장: {filepath}")
            
        except Exception as e:
            logger.error(f"성능 프로파일 저장 실패: {e}")

class EnhancedFFmpegVideoWriter:
    """확장된 FFmpeg 기반 비디오 라이터"""
    
    def __init__(self, filepath: str, fps: float, width: int, height: int, config: RTSPConfig):
        self.filepath = filepath
        self.fps = fps
        self.width = width
        self.height = height
        self.config = config
        self.process = None
        self.is_opened = False
        self.frame_count = 0
        
        # FFmpeg 설치 확인
        if not self._check_ffmpeg():
            raise RuntimeError("FFmpeg가 설치되지 않았습니다. FFmpeg를 설치해주세요.")
        
        self._start_ffmpeg()
    
    def _check_ffmpeg(self):
        """FFmpeg 설치 확인"""
        try:
            result = subprocess.run(['ffmpeg', '-version'], 
                                  capture_output=True, text=True, timeout=5)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def _get_codec_settings(self):
        """코덱별 설정 반환"""
        codec_settings = {
            # H.264 코덱들
            'libx264': {
                'codec': 'libx264',
                'pixel_formats': ['yuv420p', 'yuv422p', 'yuv444p'],
                'profiles': ['baseline', 'main', 'high'],
                'levels': ['3.0', '3.1', '4.0', '4.1', '5.0', '5.1'],
                'tunes': ['film', 'animation', 'grain', 'stillimage', 'psnr', 'ssim', 'fastdecode', 'zerolatency']
            },
            # H.265 코덱들
            'libx265': {
                'codec': 'libx265',
                'pixel_formats': ['yuv420p', 'yuv422p', 'yuv444p', 'yuv420p10le'],
                'profiles': ['main', 'main10', 'main444-8', 'main444-10'],
                'levels': ['3.0', '3.1', '4.0', '4.1', '5.0', '5.1', '6.0'],
                'tunes': ['psnr', 'ssim', 'grain', 'zerolatency', 'fastdecode']
            },
            # VP9 코덱
            'libvpx-vp9': {
                'codec': 'libvpx-vp9',
                'pixel_formats': ['yuv420p', 'yuv422p', 'yuv444p'],
                'profiles': ['0', '1', '2', '3'],
                'levels': ['10', '11', '20', '21', '30', '31', '40', '41', '50', '51', '60', '61'],
                'tunes': ['none']
            },
            # AV1 코덱
            'libaom-av1': {
                'codec': 'libaom-av1',
                'pixel_formats': ['yuv420p', 'yuv422p', 'yuv444p'],
                'profiles': ['main', 'high', 'professional'],
                'levels': ['2.0', '2.1', '3.0', '3.1', '4.0', '4.1'],
                'tunes': ['none']
            },
            # 기타 코덱들
            'libxvid': {
                'codec': 'libxvid',
                'pixel_formats': ['yuv420p'],
                'profiles': ['none'],
                'levels': ['none'],
                'tunes': ['none']
            },
            'libx262': {
                'codec': 'libx262',
                'pixel_formats': ['yuv420p', 'yuv422p'],
                'profiles': ['simple', 'main', 'high'],
                'levels': ['low', 'main', 'high'],
                'tunes': ['none']
            }
        }
        return codec_settings.get(self.config.video_codec, codec_settings['libx264'])
    
    def _get_ffmpeg_command(self):
        """FFmpeg 명령어 생성"""
        cmd = ['ffmpeg', '-y']
        
        # 하드웨어 가속 설정
        if self.config.hardware_acceleration != "none":
            if self.config.hardware_acceleration == "nvidia":
                cmd.extend(['-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda'])
            elif self.config.hardware_acceleration == "intel":
                cmd.extend(['-hwaccel', 'qsv'])
            elif self.config.hardware_acceleration == "amd":
                cmd.extend(['-hwaccel', 'amf'])
        
        # 입력 설정
        cmd.extend([
            '-f', 'rawvideo',
            '-vcodec', 'rawvideo',
            '-s', f'{self.width}x{self.height}',
            '-pix_fmt', 'bgr24',
            '-r', str(self.fps),
            '-i', '-'
        ])
        
        # 비디오 코덱 설정
        cmd.extend(['-c:v', self.config.video_codec])
        
        # 하드웨어 가속 코덱 매핑
        if self.config.hardware_acceleration == "nvidia":
            codec_map = {
                'libx264': 'h264_nvenc',
                'libx265': 'hevc_nvenc'
            }
            if self.config.video_codec in codec_map:
                cmd[-1] = codec_map[self.config.video_codec]
        
        # 품질 모드 설정
        if self.config.quality_mode == "crf":
            # CRF 모드 (일정한 품질)
            crf_value = max(0, min(51, 23 - (self.config.compression_level - 5) * 3))
            cmd.extend(['-crf', str(crf_value)])
        elif self.config.quality_mode == "cbr":
            # CBR 모드 (일정한 비트레이트)
            cmd.extend(['-b:v', self.config.bitrate])
        elif self.config.quality_mode == "vbr":
            # VBR 모드 (가변 비트레이트)
            cmd.extend(['-b:v', self.config.bitrate])
            cmd.extend(['-maxrate', self.config.max_bitrate])
            cmd.extend(['-bufsize', self.config.buffer_size])
        
        # 프리셋 설정
        if self.config.video_codec in ['libx264', 'libx265']:
            cmd.extend(['-preset', self.config.ffmpeg_preset])
        
        # 튜닝 설정
        if self.config.ffmpeg_tune != "none" and self.config.video_codec in ['libx264', 'libx265']:
            cmd.extend(['-tune', self.config.ffmpeg_tune])
        
        # 프로파일 설정
        if self.config.ffmpeg_profile != "none":
            cmd.extend(['-profile:v', self.config.ffmpeg_profile])
        
        # 레벨 설정
        if self.config.ffmpeg_level != "none":
            cmd.extend(['-level', self.config.ffmpeg_level])
        
        # 키프레임 간격
        cmd.extend(['-g', str(self.config.keyframe_interval)])
        
        # 픽셀 포맷
        cmd.extend(['-pix_fmt', self.config.pixel_format])
        
        # 압축 레벨별 추가 설정
        if self.config.video_codec == 'libx264':
            # x264 전용 설정
            cmd.extend(['-x264-params', f'threads=auto:sliced-threads=1:aq-mode=2:me=hex:subme={self.config.compression_level}'])
        elif self.config.video_codec == 'libx265':
            # x265 전용 설정
            cmd.extend(['-x265-params', f'pools=auto:frame-threads=auto:wpp=1:pmode=1:pme=1:rd={self.config.compression_level}'])
        elif self.config.video_codec == 'libvpx-vp9':
            # VP9 전용 설정
            cmd.extend(['-cpu-used', str(9 - self.config.compression_level)])
            cmd.extend(['-row-mt', '1'])
        
        # 컨테이너별 최적화
        if self.config.container_format == 'mp4':
            cmd.extend(['-movflags', '+faststart'])
        elif self.config.container_format == 'mkv':
            cmd.extend(['-avoid_negative_ts', 'make_zero'])
        
        # 추가 옵션
        if self.config.extra_options:
            extra_opts = self.config.extra_options.split()
            cmd.extend(extra_opts)
        
        # 출력 파일
        cmd.append(self.filepath)
        
        return cmd
    
    def _start_ffmpeg(self):
        """FFmpeg 프로세스 시작"""
        try:
            cmd = self._get_ffmpeg_command()
            logger.info(f"FFmpeg 명령어: {' '.join(cmd)}")
            
            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0
            )
            
            # 프로세스가 제대로 시작되었는지 확인
            import time
            time.sleep(0.1)  # 짧은 대기
            
            if self.process.poll() is not None:
                # 프로세스가 이미 종료됨
                try:
                    stderr_output = self.process.stderr.read().decode('utf-8', errors='ignore')
                    stdout_output = self.process.stdout.read().decode('utf-8', errors='ignore')
                    logger.error(f"FFmpeg 프로세스 즉시 종료: 코드 {self.process.poll()}")
                    if stderr_output:
                        logger.error(f"FFmpeg stderr: {stderr_output}")
                    if stdout_output:
                        logger.error(f"FFmpeg stdout: {stdout_output}")
                except:
                    pass
                self.is_opened = False
                return
            
            self.is_opened = True
            logger.info(f"FFmpeg 프로세스 시작됨: {self.filepath}")
            logger.info(f"비디오 설정: {self.width}x{self.height} @ {self.fps}fps")
            
        except Exception as e:
            logger.error(f"FFmpeg 프로세스 시작 실패: {e}")
            logger.error(f"설정: {self.width}x{self.height} @ {self.fps}fps, 코덱: {self.config.video_codec}")
            self.is_opened = False
    
    def write(self, frame: np.ndarray):
        """프레임 쓰기"""
        if not self.is_opened or not self.process:
            logger.warning(f"FFmpeg writer가 열려있지 않음: is_opened={self.is_opened}, process={self.process is not None}")
            return False
        
        try:
            # FFmpeg 프로세스 상태 확인
            if self.process.poll() is not None:
                logger.error(f"FFmpeg 프로세스가 종료됨: 종료 코드 {self.process.poll()}")
                # stderr 출력 읽기
                if self.process.stderr:
                    try:
                        stderr_output = self.process.stderr.read().decode('utf-8', errors='ignore')
                        if stderr_output:
                            logger.error(f"FFmpeg stderr: {stderr_output}")
                    except:
                        pass
                self.is_opened = False
                return False
            
            # 프레임 크기 검증
            if frame is None or frame.size == 0:
                logger.error(f"잘못된 프레임: shape={getattr(frame, 'shape', 'None')}")
                return False
            
            # 예상되는 프레임 크기와 비교
            expected_height, expected_width = self.height, self.width
            actual_height, actual_width = frame.shape[:2]
            if actual_height != expected_height or actual_width != expected_width:
                logger.warning(f"프레임 크기 불일치: 예상 {expected_width}x{expected_height}, 실제 {actual_width}x{actual_height}")
                # 크기 조정
                frame = cv2.resize(frame, (expected_width, expected_height))
            
            # 프레임을 바이트로 변환
            frame_bytes = frame.tobytes()
            
            # stdin이 열려있는지 확인
            if self.process.stdin.closed:
                logger.error("FFmpeg stdin이 닫혀있음")
                self.is_opened = False
                return False
            
            self.process.stdin.write(frame_bytes)
            self.process.stdin.flush()  # 버퍼 플러시 추가
            self.frame_count += 1
            return True
            
        except BrokenPipeError as e:
            logger.error(f"FFmpeg 파이프 끊어짐: {e}")
            self.is_opened = False
            return False
        except Exception as e:
            logger.error(f"FFmpeg 프레임 쓰기 실패: {e}")
            logger.error(f"파일: {self.filepath}, 프레임 #{self.frame_count}")
            # 프로세스 상태 추가 정보
            if self.process:
                logger.error(f"프로세스 상태: poll={self.process.poll()}, stdin_closed={self.process.stdin.closed if self.process.stdin else 'None'}")
            return False
    
    def release(self):
        """리소스 해제"""
        if self.process:
            try:
                self.process.stdin.close()
                self.process.wait(timeout=10)
                logger.info(f"FFmpeg 프로세스 종료됨: {self.filepath} ({self.frame_count} 프레임)")
            except subprocess.TimeoutExpired:
                logger.warning(f"FFmpeg 프로세스 강제 종료: {self.filepath}")
                self.process.kill()
            except Exception as e:
                logger.error(f"FFmpeg 프로세스 종료 오류: {e}")
            finally:
                self.process = None
        
        self.is_opened = False
    
    def isOpened(self):
        """열림 상태 확인"""
        return self.is_opened and self.process is not None

class RTSPProcessor:
    """RTSP 스트림 처리 클래스"""
    
    def __init__(self, config: RTSPConfig):
        self.config = config
        self.frame_counter = FrameCounter()
        self.threads = []
        self.running = False
        self.processing_queue = queue.Queue(maxsize=config.processing_queue_size)
        self.preview_queue = {}  # 쓰레드별 미리보기 큐
        self.thread_stats = {}  # 쓰레드별 통계
        self.connection_status = {}  # 연결 상태
        self.blur_modules = {}  # 스레드별 사용자 블러 모듈 인스턴스
        self.video_writers = {}  # 비디오 저장용
        self.frame_count = {}  # 쓰레드별 프레임 카운트
        self.video_start_time = {}  # 쓰레드별 비디오 시작 시간
        self.video_file_counter = {}  # 쓰레드별 파일 카운터
        self.video_frame_count = {}  # 비디오별 프레임 카운트
        
        # 🆕 리소스 모니터링 및 성능 프로파일링
        self.resource_monitor = ResourceMonitor()
        self.performance_profiler = PerformanceProfiler()
        
        # 저장 폴더 생성
        if config.save_enabled:
            os.makedirs(config.save_path, exist_ok=True)
        
        # FFmpeg 확인
        if config.save_enabled and config.container_format in ['mp4', 'mkv', 'webm', 'avi']:
            if not self._check_ffmpeg():
                logger.warning("FFmpeg가 설치되지 않았습니다. OpenCV VideoWriter를 사용합니다.")
        
        # 최대 10개 쓰레드까지 지원
        for i in range(10):
            self.preview_queue[i] = queue.Queue(maxsize=config.preview_queue_size)
            self.thread_stats[i] = FrameCounter()
            self.connection_status[i] = {'connected': False, 'last_frame_time': 0}
            self.frame_count[i] = 0
            self.video_start_time[i] = None
            self.video_file_counter[i] = 0
            self.video_frame_count[i] = 0
        
        # 블러 모듈 경로 저장 (스레드별로 로드됨)
        self.blur_module_path = config.blur_module_path
    
    def _check_ffmpeg(self):
        """FFmpeg 설치 확인"""
        try:
            result = subprocess.run(['ffmpeg', '-version'], 
                                  capture_output=True, text=True, timeout=5)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def load_blur_module_for_thread(self, thread_id: int):
        """스레드별 사용자 블러 모듈 로드"""
        if not self.blur_module_path:
            logger.info(f"스레드 {thread_id}: 블러 모듈 경로가 설정되지 않음")
            return
            
        try:
            spec = importlib.util.spec_from_file_location(f"blur_module_{thread_id}", self.blur_module_path)
            blur_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(blur_module)
            
            # HeadBlurrer 클래스가 있는지 확인하고 인스턴스 생성
            if hasattr(blur_module, 'HeadBlurrer'):
                # 스레드별로 개별 HeadBlurrer 인스턴스 생성
                head_blurrer = blur_module.HeadBlurrer()
                
                # apply_blur 메서드를 가진 래퍼 객체 생성
                class BlurWrapper:
                    def __init__(self, head_blurrer):
                        self.head_blurrer = head_blurrer
                    
                    def apply_blur(self, frame, thread_id):
                        return self.head_blurrer.process_frame(frame)
                
                self.blur_modules[thread_id] = BlurWrapper(head_blurrer)
                logger.info(f"스레드 {thread_id}: 블러 모듈(HeadBlurrer) 인스턴스 로드 성공")
                
            elif hasattr(blur_module, 'apply_blur'):
                # 직접 apply_blur 함수가 있는 경우
                self.blur_modules[thread_id] = blur_module
                logger.info(f"스레드 {thread_id}: 블러 모듈(function) 로드 성공")
            else:
                logger.error(f"스레드 {thread_id}: 블러 모듈에 'HeadBlurrer' 클래스나 'apply_blur' 함수가 없습니다.")
                
        except Exception as e:
            logger.error(f"스레드 {thread_id}: 블러 모듈 로드 실패 - {e}")
            import traceback
            logger.error(f"상세 오류: {traceback.format_exc()}")
    
    def get_source_for_thread(self, thread_id: int) -> str:
        """쓰레드 ID에 따른 소스 반환"""
        if not self.config.sources:
            raise ValueError("소스가 설정되지 않았습니다.")
        
        # 소스 개수로 나눈 나머지로 순환
        source_index = thread_id % len(self.config.sources)
        return self.config.sources[source_index]
    
    def is_rtsp_source(self, source: str) -> bool:
        """RTSP 소스인지 확인"""
        return source.lower().startswith(('rtsp://', 'http://', 'https://'))
    
    def connect_to_source(self, source: str, thread_id: int) -> cv2.VideoCapture:
        """소스에 연결 (RTSP 또는 파일)"""
        if self.is_rtsp_source(source):
            logger.info(f"쓰레드 {thread_id}: RTSP 연결 시도 - {source}")
        else:
            logger.info(f"쓰레드 {thread_id}: 파일 읽기 시도 - {source}")
        
        cap = cv2.VideoCapture(source)
        
        # 연결 설정
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        # FPS 설정
        if self.config.force_fps:
            cap.set(cv2.CAP_PROP_FPS, self.config.input_fps)
            logger.info(f"쓰레드 {thread_id}: FPS 강제 설정 - {self.config.input_fps}")
        
        if self.is_rtsp_source(source):
            # RTSP 전용 설정
            if not self.config.force_fps:
                cap.set(cv2.CAP_PROP_FPS, self.config.input_fps)
            try:
                cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, self.config.connection_timeout * 1000)
                cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000)
            except:
                pass
        
        # 연결 확인
        if not cap.isOpened():
            raise ConnectionError(f"소스 연결 실패: {source}")
        
        # 첫 번째 프레임 읽기 시도
        ret, frame = cap.read()
        if not ret:
            cap.release()
            raise ConnectionError(f"소스에서 프레임 읽기 실패: {source}")
        
        # 실제 FPS 확인 및 로그
        actual_fps = cap.get(cv2.CAP_PROP_FPS)
        if actual_fps > 0:
            logger.info(f"쓰레드 {thread_id}: 실제 FPS - {actual_fps:.1f}")
        
        logger.info(f"쓰레드 {thread_id}: 소스 연결 성공 - {source}")
        self.connection_status[thread_id]['connected'] = True
        return cap
    
    def process_frame(self, frame: np.ndarray, thread_id: int) -> np.ndarray:
        """프레임 처리 (사용자 블러 모듈 사용)"""
        try:
            # 🆕 성능 측정 시작 (고성능 모드가 아닌 경우에만)
            if not self.config.high_performance_mode:
                self.performance_profiler.start_profile("frame_processing", thread_id)
            
            # 고성능 모드에서는 프레임 복사 최소화
            if self.config.high_performance_mode:
                processed_frame = frame  # 복사 대신 참조 사용
            else:
                processed_frame = frame.copy()
            
            # 영상 처리가 활성화된 경우에만 처리
            if self.config.enable_processing:
                # 🆕 블러 처리 (블러가 활성화된 경우에만)
                if self.config.blur_enabled:
                    # 🆕 블러 처리 성능 측정 시작 (고성능 모드가 아닌 경우에만)
                    if not self.config.high_performance_mode:
                        self.performance_profiler.start_profile("blur_processing", thread_id)
                    
                    # 스레드별 사용자 블러 모듈 적용
                    if thread_id in self.blur_modules and hasattr(self.blur_modules[thread_id], 'apply_blur'):
                        try:
                            processed_frame = self.blur_modules[thread_id].apply_blur(processed_frame, thread_id)
                            logger.debug(f"쓰레드 {thread_id}: 사용자 블러 처리 완료")
                        except Exception as e:
                            logger.error(f"쓰레드 {thread_id}: 사용자 블러 처리 오류 - {e}")
                            # 블러 처리 실패 시 기본 처리
                            processed_frame = cv2.GaussianBlur(frame, (15, 15), 0)
                    else:
                        # 기본 블러 처리 (블러 모듈이 없거나 로드 실패한 경우)
                        processed_frame = cv2.GaussianBlur(frame, (15, 15), 0)
                        if thread_id not in self.blur_modules:
                            logger.debug(f"쓰레드 {thread_id}: 블러 모듈이 로드되지 않아 기본 블러 적용")
                    
                    # 🆕 블러 처리 성능 측정 종료 (고성능 모드가 아닌 경우에만)
                    if not self.config.high_performance_mode:
                        self.performance_profiler.end_profile("blur_processing", thread_id)
                else:
                    # 블러 비활성화 시 원본 프레임 사용
                    logger.debug(f"쓰레드 {thread_id}: 블러 처리 비활성화됨")
                
                # 🆕 오버레이 처리 (고성능 모드가 아닌 경우에만)
                if not self.config.high_performance_mode:
                    # 🆕 오버레이 처리 성능 측정 시작
                    self.performance_profiler.start_profile("overlay_processing", thread_id)
                    
                    # 오버레이 정보 추가 (왼쪽 상단)
                    if self.config.overlay_enabled:
                        frame_number = self.frame_count[thread_id] + 1
                        current_time = time.strftime("%Y-%m-%d %H:%M:%S")
                        latitude = self.config.latitude
                        longitude = self.config.longitude
                        
                        # 오버레이 텍스트 생성
                        overlay_lines = [
                            f"Frame: {frame_number:06d}",
                            f"Time: {current_time}",
                            f"GPS: {latitude:.4f}, {longitude:.4f}",
                            f"Thread: {thread_id}"
                        ]
                        
                        # 반투명 배경 추가
                        for i, line in enumerate(overlay_lines):
                            y_pos = 25 + i * 25
                            (text_width, text_height), _ = cv2.getTextSize(line, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
                            bg_rect = np.zeros((text_height + 10, text_width + 10, 3), dtype=np.uint8)
                            processed_frame[y_pos-text_height-2:y_pos+8, 5:5+text_width+10] = cv2.addWeighted(
                                processed_frame[y_pos-text_height-2:y_pos+8, 5:5+text_width+10], 0.5, bg_rect, 0.5, 0
                            )
                            
                            # 텍스트 오버레이
                            y_pos = 25 + i * 25
                            cv2.putText(processed_frame, line, (10, y_pos), 
                                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 1, cv2.LINE_AA)
                    else:
                        # 오버레이 비활성화 시 기본 텍스트만
                        text = f"Thread {thread_id} - Processed"
                        cv2.putText(processed_frame, text, (10, 30), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    
                    # 🆕 오버레이 처리 성능 측정 종료
                    self.performance_profiler.end_profile("overlay_processing", thread_id)
                
                # 🆕 저장 처리 성능 측정 시작 (고성능 모드가 아닌 경우에만)
                if self.config.save_enabled:
                    if not self.config.high_performance_mode:
                        self.performance_profiler.start_profile("save_processing", thread_id)
                    self.save_frame(processed_frame, thread_id)
                    if not self.config.high_performance_mode:
                        self.performance_profiler.end_profile("save_processing", thread_id)
                
                # 🆕 프레임 처리 성능 측정 종료 (고성능 모드가 아닌 경우에만)
                if not self.config.high_performance_mode:
                    self.performance_profiler.end_profile("frame_processing", thread_id)
                
                return processed_frame
            
        except Exception as e:
            logger.error(f"쓰레드 {thread_id}: 프레임 처리 오류 - {e}")
            
            # 🆕 기본 통계는 항상, 세부 통계는 고성능 모드가 아닌 경우에만
            self.frame_counter.increment_error()  # 전체 통계는 항상 업데이트
            if not self.config.high_performance_mode:
                self.thread_stats[thread_id].increment_error()  # 스레드별 통계는 고성능 모드에서 제외
                
                # 🆕 오류 발생 시에도 성능 측정 종료
                self.performance_profiler.end_profile("frame_processing", thread_id)
            
            # 오류 발생 시에도 저장 시도
            if self.config.save_enabled:
                self.save_frame(frame, thread_id)
            return frame
    
    def save_frame(self, frame: np.ndarray, thread_id: int):
        """프레임 저장"""
        try:
            # 저장이 비활성화되어 있으면 리턴
            if not self.config.save_enabled:
                return
            
            # 저장 경로 확인 및 생성
            if not os.path.exists(self.config.save_path):
                os.makedirs(self.config.save_path, exist_ok=True)
                logger.info(f"저장 경로 생성: {self.config.save_path}")
                
            self.frame_count[thread_id] += 1
            
            # 영상으로만 저장 (이미지 저장 비활성화)
            if self.config.container_format in ['mp4', 'mkv', 'webm', 'avi']:
                # 비디오 저장 (FFmpeg 또는 OpenCV)
                self.save_to_video_batch(frame, thread_id)
            else:
                # 지원하지 않는 포맷 - 영상 저장만 지원
                logger.warning(f"쓰레드 {thread_id}: 지원하지 않는 포맷 '{self.config.container_format}', MP4로 저장")
                # MP4로 강제 저장
                original_format = self.config.container_format
                self.config.container_format = "mp4"
                self.save_to_video_batch(frame, thread_id)
                self.config.container_format = original_format
            
            # 저장 성공 시 통계 업데이트
            self.thread_stats[thread_id].increment_saved()
            self.frame_counter.increment_saved()
            
        except Exception as e:
            logger.error(f"쓰레드 {thread_id}: 프레임 저장 오류 - {e}")
            import traceback
            logger.error(f"상세 오류: {traceback.format_exc()}")
    
    def save_to_image(self, frame: np.ndarray, thread_id: int):
        """이미지로 저장"""
        try:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            
            # 이미지 확장자 결정 (비디오 포맷인 경우 jpg로 강제 변경)
            if self.config.save_format in ['mp4', 'mkv', 'webm', 'avi']:
                image_format = "jpg"
                logger.debug(f"쓰레드 {thread_id}: 비디오 포맷({self.config.save_format})에서 이미지 저장으로 폴백, jpg 사용")
            elif self.config.save_format in ['jpg', 'jpeg', 'png', 'bmp', 'tiff']:
                image_format = self.config.save_format
            else:
                image_format = "jpg"  # 기본값
                logger.debug(f"쓰레드 {thread_id}: 알 수 없는 포맷({self.config.save_format}), jpg 사용")
            
            filename = f"thread_{thread_id:02d}_{timestamp}_{self.frame_count[thread_id]:06d}.{image_format}"
            filepath = os.path.join(self.config.save_path, filename)
            
            # 이미지 품질 설정 (JPEG인 경우)
            save_params = []
            if image_format.lower() in ['jpg', 'jpeg']:
                save_params = [cv2.IMWRITE_JPEG_QUALITY, 95]
            elif image_format.lower() == 'png':
                save_params = [cv2.IMWRITE_PNG_COMPRESSION, 1]
            
            success = cv2.imwrite(filepath, frame, save_params)
            if success:
                logger.info(f"쓰레드 {thread_id}: 이미지 저장 완료 - {filename}")
            else:
                logger.error(f"쓰레드 {thread_id}: 이미지 저장 실패 - {filename}")
                
        except Exception as e:
            logger.error(f"쓰레드 {thread_id}: 이미지 저장 오류 - {e}")
            # 최후의 수단: 기본 jpg로 저장 시도
            try:
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                fallback_filename = f"thread_{thread_id:02d}_{timestamp}_{self.frame_count[thread_id]:06d}_fallback.jpg"
                fallback_filepath = os.path.join(self.config.save_path, fallback_filename)
                success = cv2.imwrite(fallback_filepath, frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
                if success:
                    logger.info(f"쓰레드 {thread_id}: 폴백 이미지 저장 성공 - {fallback_filename}")
                else:
                    logger.error(f"쓰레드 {thread_id}: 폴백 이미지 저장도 실패")
            except Exception as fallback_error:
                logger.error(f"쓰레드 {thread_id}: 폴백 이미지 저장 중 오류 - {fallback_error}")
    
    def save_to_video_batch(self, frame: np.ndarray, thread_id: int):
        """비디오로 저장 (Enhanced FFmpeg 또는 OpenCV)"""
        try:
            # 새 비디오 시작 조건: 처음이거나 설정된 간격만큼 프레임이 쌓였을 때
            if (thread_id not in self.video_writers or 
                self.video_frame_count[thread_id] >= self.config.save_interval):
                
                # 기존 비디오 writer 종료
                if thread_id in self.video_writers:
                    try:
                        self.video_writers[thread_id].release()
                        logger.info(f"쓰레드 {thread_id}: 비디오 저장 완료 - {self.video_frame_count[thread_id]}프레임 "
                                  f"(part{self.video_file_counter[thread_id]:03d})")
                    except Exception as e:
                        logger.error(f"쓰레드 {thread_id}: 기존 writer 해제 오류 - {e}")
                    finally:
                        if thread_id in self.video_writers:
                            del self.video_writers[thread_id]
                
                # 새 비디오 파일 시작
                self.video_file_counter[thread_id] += 1
                self.video_frame_count[thread_id] = 0
                
                # 파일명 생성
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filename = f"thread_{thread_id:02d}_{timestamp}_part{self.video_file_counter[thread_id]:03d}.{self.config.container_format}"
                filepath = os.path.join(self.config.save_path, filename)
                
                # 비디오 writer 초기화
                height, width = frame.shape[:2]
                fps = max(1.0, self.config.input_fps)
                
                logger.info(f"쓰레드 {thread_id}: 비디오 writer 생성 시작")
                logger.info(f"  파일: {filename}")
                logger.info(f"  해상도: {width}x{height} @ {fps}fps")
                logger.info(f"  컨테이너: {self.config.container_format}")
                
                writer_created = False
                
                # 1차 시도: Enhanced FFmpeg (항상 우선 시도)
                if self._check_ffmpeg():
                    try:
                        logger.info(f"쓰레드 {thread_id}: Enhanced FFmpeg writer 생성 시도")
                        self.video_writers[thread_id] = EnhancedFFmpegVideoWriter(filepath, fps, width, height, self.config)
                        
                        if self.video_writers[thread_id].isOpened():
                            logger.info(f"쓰레드 {thread_id}: ✅ Enhanced FFmpeg 비디오 시작 성공 - {filename}")
                            logger.info(f"  🎬 코덱: {self.config.video_codec}")
                            logger.info(f"  📊 압축 레벨: {self.config.compression_level}")
                            logger.info(f"  ⚙️ 품질 모드: {self.config.quality_mode}")
                            logger.info(f"  💾 비트레이트: {self.config.bitrate}")
                            writer_created = True
                        else:
                            raise Exception("Enhanced FFmpeg writer가 열리지 않음")
                            
                    except Exception as e:
                        logger.warning(f"쓰레드 {thread_id}: Enhanced FFmpeg writer 생성 실패 - {e}")
                        logger.info(f"쓰레드 {thread_id}: OpenCV VideoWriter로 폴백 시도")
                        if thread_id in self.video_writers:
                            try:
                                self.video_writers[thread_id].release()
                            except:
                                pass
                            del self.video_writers[thread_id]
                else:
                    logger.warning(f"쓰레드 {thread_id}: FFmpeg 사용 불가, OpenCV VideoWriter 사용")
                
                # 2차 시도: OpenCV VideoWriter (FFmpeg 실패 시 또는 이미지 포맷인 경우)
                if not writer_created:
                    logger.info(f"쓰레드 {thread_id}: OpenCV VideoWriter 생성 시도")
                    
                    # 다양한 fourcc 코덱 시도 (안정성 순서로 정렬)
                    fourcc_options = []
                    
                    if self.config.container_format == 'mp4':
                        # MP4: 가장 안정적인 코덱들만 사용 (H264/AVC1 제외)
                        fourcc_options = ['mp4v', 'MJPG', 'XVID']
                    elif self.config.container_format == 'avi':
                        # AVI: 호환성이 가장 좋은 코덱들
                        fourcc_options = ['XVID', 'MJPG', 'mp4v']
                    elif self.config.container_format == 'mkv':
                        # MKV: 다양한 코덱 지원
                        fourcc_options = ['XVID', 'mp4v', 'MJPG']
                    elif self.config.container_format == 'webm':
                        # WebM: VP8/VP9 우선, 폴백
                        fourcc_options = ['VP80', 'VP90', 'MJPG']
                    else:
                        # 기타 포맷: 가장 호환성 좋은 코덱들
                        fourcc_options = ['MJPG', 'XVID', 'mp4v']
                    
                    for fourcc_str in fourcc_options:
                        try:
                            logger.info(f"쓰레드 {thread_id}: {fourcc_str} 코덱으로 OpenCV VideoWriter 시도")
                            
                            # FourCC 코드 생성
                            try:
                                fourcc = cv2.VideoWriter_fourcc(*fourcc_str)
                            except Exception as fourcc_error:
                                logger.warning(f"쓰레드 {thread_id}: {fourcc_str} 코덱 지원하지 않음 - {fourcc_error}")
                                continue
                            
                            # 파일 확장자를 코덱에 맞게 조정
                            if fourcc_str in ['MJPG', 'DIVX']:
                                test_filepath = filepath.replace(f'.{self.config.container_format}', '.avi')
                            elif fourcc_str in ['VP80', 'VP90']:
                                test_filepath = filepath.replace(f'.{self.config.container_format}', '.webm')
                            else:
                                test_filepath = filepath
                            
                            logger.debug(f"쓰레드 {thread_id}: {fourcc_str} 코덱으로 {test_filepath} 생성 시도")
                            
                            # VideoWriter 생성 (타임아웃 방지를 위한 빠른 체크)
                            writer = None
                            try:
                                writer = cv2.VideoWriter(test_filepath, fourcc, fps, (width, height))
                                
                                if not writer.isOpened():
                                    logger.warning(f"쓰레드 {thread_id}: {fourcc_str} 코덱으로 VideoWriter 열기 실패")
                                    if writer:
                                        writer.release()
                                    continue
                                
                                # writer가 정상적으로 열렸는지만 확인 (실제 쓰기 테스트 제거)
                                self.video_writers[thread_id] = writer
                                logger.info(f"쓰레드 {thread_id}: ✅ OpenCV 비디오 시작 성공 - {os.path.basename(test_filepath)} ({fourcc_str})")
                                writer_created = True
                                break
                                    
                            except Exception as writer_error:
                                logger.warning(f"쓰레드 {thread_id}: {fourcc_str} VideoWriter 생성 중 오류 - {writer_error}")
                                if writer:
                                    try:
                                        writer.release()
                                    except:
                                        pass
                                continue
                                
                        except Exception as e:
                            logger.error(f"쓰레드 {thread_id}: {fourcc_str} 코덱 시도 중 전체 오류 - {e}")
                            continue
                    
                    if not writer_created:
                        logger.error(f"쓰레드 {thread_id}: 모든 VideoWriter 생성 시도 실패 (시도한 코덱: {', '.join(fourcc_options)})")
                        logger.error(f"쓰레드 {thread_id}: 영상 저장 불가 - 프레임 건너뜀")
                        # 영상 저장만 지원하므로 이미지 폴백 제거
                        return
                
                # 최종 확인
                if thread_id not in self.video_writers or not self.video_writers[thread_id].isOpened():
                    logger.error(f"쓰레드 {thread_id}: 비디오 writer 생성 최종 실패")
                    if thread_id in self.video_writers:
                        del self.video_writers[thread_id]
                    return
            
            # 프레임을 비디오에 추가
            if thread_id in self.video_writers and self.video_writers[thread_id].isOpened():
                try:
                    success = self.video_writers[thread_id].write(frame)
                    if success:
                        self.video_frame_count[thread_id] += 1
                        
                        # 1프레임마다 또는 100프레임마다 로그 출력
                        if self.video_frame_count[thread_id] == 1 or self.video_frame_count[thread_id] % 100 == 0:
                            logger.info(f"쓰레드 {thread_id}: 비디오 프레임 추가 - "
                                       f"{self.video_frame_count[thread_id]}/{self.config.save_interval}")
                    else:
                        logger.error(f"쓰레드 {thread_id}: 비디오 프레임 쓰기 실패")
                        logger.error(f"쓰레드 {thread_id}: 프레임 정보 - shape={frame.shape}, dtype={frame.dtype}")
                        
                        # Writer 상태 확인 및 복구
                        writer = self.video_writers[thread_id]
                        
                        # Enhanced FFmpeg writer인 경우
                        if hasattr(writer, 'process') and writer.process:
                            poll_status = writer.process.poll()
                            logger.error(f"쓰레드 {thread_id}: FFmpeg 프로세스 상태 - poll={poll_status}")
                            if poll_status is not None:
                                logger.error(f"쓰레드 {thread_id}: FFmpeg 프로세스 종료됨, writer 재생성 예정")
                        else:
                            # OpenCV VideoWriter인 경우
                            logger.error(f"쓰레드 {thread_id}: OpenCV VideoWriter 쓰기 실패, writer 재생성 예정")
                        
                        # Writer 정리 후 다음 프레임에서 재생성
                        try:
                            writer.release()
                        except Exception as release_error:
                            logger.error(f"쓰레드 {thread_id}: Writer 해제 오류 - {release_error}")
                        
                        del self.video_writers[thread_id]
                        self.video_frame_count[thread_id] = self.config.save_interval  # 다음 프레임에서 새 파일 생성
                        
                        # 영상 저장 실패 시 프레임 건너뜀 (이미지 백업 제거)
                        logger.warning(f"쓰레드 {thread_id}: 영상 저장 실패로 프레임 건너뜀")
                        
                except Exception as write_error:
                    logger.error(f"쓰레드 {thread_id}: 프레임 쓰기 중 예외 발생 - {write_error}")
                    # Writer 정리
                    if thread_id in self.video_writers:
                        try:
                            self.video_writers[thread_id].release()
                        except:
                            pass
                        del self.video_writers[thread_id]
                    
                    # 영상 저장 오류 시 프레임 건너뜀 (이미지 백업 제거)
                    logger.warning(f"쓰레드 {thread_id}: 영상 저장 오류로 프레임 건너뜀")
            else:
                if thread_id not in self.video_writers:
                    logger.debug(f"쓰레드 {thread_id}: 비디오 writer가 없음 (다음 프레임에서 생성됨)")
                else:
                    logger.error(f"쓰레드 {thread_id}: 비디오 writer가 열려있지 않음")
                    # Writer 정리
                    if thread_id in self.video_writers:
                        try:
                            self.video_writers[thread_id].release()
                        except:
                            pass
                        del self.video_writers[thread_id]
                
        except Exception as e:
            logger.error(f"쓰레드 {thread_id}: 비디오 저장 중 전체 오류 - {e}")
            import traceback
            logger.error(f"상세 오류: {traceback.format_exc()}")
            
            # Writer 정리
            if thread_id in self.video_writers:
                try:
                    self.video_writers[thread_id].release()
                except:
                    pass
                del self.video_writers[thread_id]
            
            # 예외 발생 시 프레임 건너뜀 (이미지 백업 제거)
            logger.warning(f"쓰레드 {thread_id}: 예외 발생으로 프레임 건너뜀")
    
    def source_receiver(self, thread_id: int):
        """소스 수신 쓰레드 (RTSP 또는 파일)"""
        source = self.get_source_for_thread(thread_id)
        source_name = self.extract_source_name(source)
        
        logger.info(f"소스 수신 쓰레드 {thread_id} 시작 ({source_name})")
        
        # 🆕 스레드별 블러 모듈 로드
        try:
            self.load_blur_module_for_thread(thread_id)
        except Exception as e:
            logger.error(f"스레드 {thread_id}: 블러 모듈 로드 중 오류 - {e}")
        
        cap = None
        frames_received = 0
        consecutive_failures = 0
        
        # FPS 기반 프레임 간격 계산
        frame_interval = 1.0 / self.config.input_fps
        start_time = time.time()  # 스레드 시작 시간 기록
        
        # 스레드 시작 시간을 connection_status에 저장
        if thread_id not in self.connection_status:
            self.connection_status[thread_id] = {}
        self.connection_status[thread_id]['start_time'] = start_time
        
        while self.running:
            try:
                # 연결 시도
                if cap is None or not cap.isOpened():
                    cap = self.connect_to_source(source, thread_id)
                    consecutive_failures = 0
                
                # FPS 제어를 위한 대기 (시작 시간 기준)
                next_frame_time = start_time + (frames_received + 1) * frame_interval
                sleep_time = next_frame_time - time.time()
                
                if sleep_time > 0:
                    time.sleep(sleep_time)
                
                # 프레임 읽기
                ret, frame = cap.read()
                
                if not ret:
                    logger.warning(f"쓰레드 {thread_id}: 프레임 읽기 실패 ({source_name})")
                    # 🆕 기본 통계는 항상, 세부 통계는 고성능 모드가 아닌 경우에만
                    self.frame_counter.increment_lost()  # 전체 통계는 항상 업데이트
                    if not self.config.high_performance_mode:
                        self.thread_stats[thread_id].increment_lost()  # 스레드별 통계는 고성능 모드에서 제외
                    consecutive_failures += 1
                    
                    if consecutive_failures > 10:
                        logger.error(f"쓰레드 {thread_id}: 연속 실패로 재연결 시도 ({source_name})")
                        if cap:
                            cap.release()
                        cap = None
                        
                        # 파일인 경우 처음부터 다시 시작
                        if not self.is_rtsp_source(source):
                            time.sleep(1)
                        else:
                            time.sleep(self.config.reconnect_interval)
                            
                        consecutive_failures = 0
                    continue
                
                # 최대 처리 시간 체크
                if self.config.max_duration_seconds:
                    elapsed_time = time.time() - start_time
                    if elapsed_time >= self.config.max_duration_seconds:
                        break
                
                # 🆕 프레임 통계 업데이트 (기본 통계는 항상, 세부 통계는 고성능 모드가 아닌 경우에만)
                self.frame_counter.increment_received()  # 전체 통계는 항상 업데이트
                if not self.config.high_performance_mode:
                    self.thread_stats[thread_id].increment_received()  # 스레드별 통계는 고성능 모드에서 제외
                    self.connection_status[thread_id]['last_frame_time'] = time.time()
                
                # 프레임 처리
                processed_frame = self.process_frame(frame, thread_id)
                
                # 🆕 프레임 로스 시뮬레이션 (기본 통계는 항상, 로깅은 고성능 모드가 아닌 경우에만)
                if random.random() < self.config.frame_loss_rate:
                    self.frame_counter.increment_lost()  # 전체 통계는 항상 업데이트
                    if not self.config.high_performance_mode:
                        self.thread_stats[thread_id].increment_lost()  # 스레드별 통계는 고성능 모드에서 제외
                        logger.debug(f"쓰레드 {thread_id}: 프레임 {frames_received} 시뮬레이션 손실 ({source_name})")
                    continue
                
                # 처리된 프레임을 미리보기 큐에 추가 (미리보기가 활성화된 경우에만)
                if self.config.preview_enabled:
                    try:
                        # 고성능 모드에서는 프레임 복사 생략
                        if self.config.high_performance_mode:
                            self.preview_queue[thread_id].put((processed_frame, source_name), block=False)
                        else:
                            self.preview_queue[thread_id].put((processed_frame.copy(), source_name), block=False)
                    except queue.Full:
                        pass
                
                # 통계 업데이트
                self.frame_counter.increment_processed()
                if not self.config.high_performance_mode:
                    self.thread_stats[thread_id].increment_processed()
                
                frames_received += 1
                
                # 로깅 (고성능 모드가 아닌 경우에만)
                if not self.config.high_performance_mode:
                    logger.debug(f"쓰레드 {thread_id}: 프레임 {frames_received} 처리 완료 ({source_name})")
                
                consecutive_failures = 0
                
            except ConnectionError as e:
                logger.error(f"쓰레드 {thread_id}: 연결 오류 - {e}")
                if not self.config.high_performance_mode:
                    self.connection_status[thread_id]['connected'] = False
                if cap:
                    cap.release()
                cap = None
                time.sleep(self.config.reconnect_interval)
                
            except Exception as e:
                logger.error(f"쓰레드 {thread_id}: 예상치 못한 오류 - {e}")
                # 🆕 기본 통계는 항상, 세부 통계는 고성능 모드가 아닌 경우에만
                self.frame_counter.increment_error()  # 전체 통계는 항상 업데이트
                if not self.config.high_performance_mode:
                    self.thread_stats[thread_id].increment_error()  # 스레드별 통계는 고성능 모드에서 제외
                time.sleep(1)
        
        # 정리
        if cap:
            cap.release()
        if thread_id in self.video_writers:
            self.video_writers[thread_id].release()
        self.connection_status[thread_id]['connected'] = False
        logger.info(f"소스 수신 쓰레드 {thread_id} 종료 ({source_name})")
    
    def extract_source_name(self, source: str) -> str:
        """소스에서 이름 추출"""
        try:
            if self.is_rtsp_source(source):
                # RTSP URL에서 이름 추출
                if '://' in source:
                    parts = source.split('://', 1)[1]
                    if '/' in parts:
                        return parts.split('/', 1)[1]
                    else:
                        return parts
            else:
                # 파일 경로에서 파일명 추출
                return os.path.basename(source)
            return source
        except:
            return source
    
    def start(self):
        """프로세서 시작"""
        logger.info("소스 프로세서 시작")
        self.running = True
        
        # 🆕 리소스 모니터링 시작
        self.resource_monitor.start_monitoring()
        self.performance_profiler.start_profile("total_processing")
        
        # 소스 수신 쓰레드들 시작
        for i in range(self.config.thread_count):
            thread = threading.Thread(
                target=self.source_receiver,
                args=(i,),
                daemon=True
            )
            thread.start()
            self.threads.append(thread)
        
        logger.info(f"소스 프로세서 시작됨 - 쓰레드 수: {self.config.thread_count}")
    
    def stop(self):
        """프로세서 중지"""
        logger.info("소스 프로세서 중지 중...")
        self.running = False
        
        # 🆕 성능 측정 종료
        self.performance_profiler.end_profile("total_processing")
        
        # 비디오 라이터 종료
        for thread_id, writer in self.video_writers.items():
            if writer and writer.isOpened():
                writer.release()
                logger.info(f"쓰레드 {thread_id}: 최종 비디오 저장 완료 - {self.video_frame_count[thread_id]}프레임")
        self.video_writers.clear()
        
        # 🆕 스레드별 블러 모듈 정리
        for thread_id in list(self.blur_modules.keys()):
            try:
                # HeadBlurrer 인스턴스가 있는 경우 정리
                if hasattr(self.blur_modules[thread_id], 'head_blurrer'):
                    del self.blur_modules[thread_id].head_blurrer
                del self.blur_modules[thread_id]
                logger.info(f"스레드 {thread_id}: 블러 모듈 정리 완료")
            except Exception as e:
                logger.error(f"스레드 {thread_id}: 블러 모듈 정리 중 오류 - {e}")
        self.blur_modules.clear()
        
        # 모든 쓰레드 종료 대기
        for thread in self.threads:
            thread.join(timeout=3.0)
        
        # 🆕 리소스 모니터링 중지
        self.resource_monitor.stop_monitoring()
        
        logger.info("소스 프로세서 중지됨")
    
    def get_statistics(self):
        """통계 정보 반환"""
        stats = self.frame_counter.get_stats()
        
        # 🆕 리소스 통계 추가
        resource_stats = self.resource_monitor.get_current_stats()
        performance_stats = self.performance_profiler.get_profile_stats()
        
        return {
            **stats,
            'thread_count': self.config.thread_count,
            'queue_size': 0,  # processing_queue 사용 안함
            'preview_queue_sizes': {k: v.qsize() for k, v in self.preview_queue.items()},
            'connection_status': self.connection_status.copy(),
            # 🆕 추가된 통계
            'resource_stats': resource_stats,
            'performance_stats': performance_stats
        }
    
    def get_thread_statistics(self, thread_id: int):
        """쓰레드별 통계 반환"""
        if thread_id in self.thread_stats:
            return self.thread_stats[thread_id].get_stats()
        return {}
    
    def reset_statistics(self):
        """통계 초기화"""
        self.frame_counter.reset()
        for thread_stat in self.thread_stats.values():
            thread_stat.reset()
        logger.info("통계 초기화됨")

class RTSPProcessorGUI:
    """RTSP 프로세서 GUI 클래스 - 스크롤 가능한 설정 패널 포함"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("RTSP/파일 프로세서 - 확장된 압축 코덱 지원")
        self.root.geometry("1800x1000")
        
        self.processor = None
        self.config = None
        self.update_thread = None
        self.running = False
        self.preview_enabled = True  # 실시간 미리보기 활성화 상태
        self.blur_enabled = True  # 블러 처리 활성화 상태
        self.high_performance_enabled = False  # 고성능 모드 활성화 상태
        self.overlay_enabled = True  # 오버레이 활성화 상태
        
        # 🆕 FPS 계산 개선을 위한 변수들
        self.processor_start_time = None  # 실제 프로세서 시작 시간
        self.fps_history = []  # 실시간 FPS 이력
        self.last_frame_count = 0
        self.last_fps_time = 0
        
        # 프로젝트 기본 폴더 생성
        self.create_project_folders()
        
        # 스크롤러블 캔버스 래퍼 생성
        self.canvas = tk.Canvas(self.root, highlightthickness=0)
        self.v_scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.v_scrollbar.set)
        
        # 스크롤바와 캔버스 배치
        self.v_scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        
        # 메인 프레임 (캔버스 안에)
        self.main_frame = ttk.Frame(self.canvas, padding="10")
        self.canvas_window = self.canvas.create_window((0, 0), window=self.main_frame, anchor="nw")
        
        # 스크롤 영역 자동 업데이트
        self.main_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        # 캔버스 크기 변경 시 프레임 너비 조정
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width)
        )
        
        # 마우스 휠 스크롤 바인딩
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-4>", self._on_mousewheel)
        self.canvas.bind("<Button-5>", self._on_mousewheel)
        
        self.setup_ui()
        self.start_update_thread()
    
    def create_project_folders(self):
        """프로젝트 기본 폴더 생성"""
        try:
            # 미디어 폴더 생성
            media_dir = "./media"
            os.makedirs(media_dir, exist_ok=True)
            logger.info(f"미디어 폴더 확인/생성: {media_dir}")
            
            # output 폴더 생성  
            output_dir = "./output"
            os.makedirs(output_dir, exist_ok=True)
            logger.info(f"출력 폴더 확인/생성: {output_dir}")
            
        except Exception as e:
            logger.error(f"프로젝트 폴더 생성 실패: {e}")
            # GUI 에러는 나중에 표시하기 위해 저장
            self.folder_creation_error = str(e)
    
    def _on_mousewheel(self, event):
        """마우스 휠 스크롤 처리"""
        if event.delta:
            # Windows
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        elif event.num == 4:
            # Linux scroll up
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            # Linux scroll down
            self.canvas.yview_scroll(1, "units")
    
    def setup_ui(self):
        """UI 설정"""
        # main_frame은 이미 __init__에서 self.main_frame으로 생성됨

        # 📋 소스 설정 프레임 -------------------------------------------
        source_frame = ttk.LabelFrame(
            self.main_frame,
            text="📋 소스 설정 (RTSP URL 또는 파일 경로)",
            padding="5"
        )
        source_frame.grid(
            row=0, column=0, columnspan=4,
            sticky=(tk.W, tk.E),
            pady=(0, 5)
        )
        source_frame.columnconfigure(1, weight=1)
        
        # 소스 입력 필드들 (최대 8개)
        self.source_vars = []
        for i in range(8):
            ttk.Label(source_frame, text=f"소스 {i+1}:").grid(row=i//2, column=(i%2)*3, sticky=tk.W, pady=2, padx=(0 if i%2==0 else 20, 0))
            source_var = tk.StringVar()
            self.source_vars.append(source_var)
            entry = ttk.Entry(source_frame, textvariable=source_var, width=50)
            entry.grid(row=i//2, column=(i%2)*3+1, sticky=(tk.W, tk.E), pady=2, padx=(5, 0))
            ttk.Button(source_frame, text="파일 선택", command=lambda idx=i: self.browse_file(idx), width=10).grid(row=i//2, column=(i%2)*3+2, sticky=tk.W, pady=2, padx=(5, 0))
        
        # 소스 관리 버튼들
        source_buttons_frame = ttk.Frame(source_frame)
        source_buttons_frame.grid(row=4, column=0, columnspan=6, sticky=(tk.W, tk.E), pady=(10, 0))
        ttk.Button(source_buttons_frame, text="📁 파일 선택", command=self.browse_multiple_files).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(source_buttons_frame, text="🗑️ 모든 소스 지우기", command=self.clear_all_sources).pack(side=tk.LEFT, padx=(0, 5))
        
        # 🎨 블러 모듈 설정 프레임 -------------------------------------
        blur_frame = ttk.LabelFrame(
            self.main_frame,
            text="🎨 사용자 블러 모듈 설정",
            padding="5"
        )
        blur_frame.grid(
            row=1, column=0, columnspan=4,
            sticky=(tk.W, tk.E),
            pady=(0, 5)
        )
        blur_frame.columnconfigure(1, weight=1)
        
        ttk.Label(blur_frame, text="블러 모듈 경로:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.blur_module_var = tk.StringVar(value=get_env_value('BLUR_MODULE_PATH', ''))
        ttk.Entry(blur_frame, textvariable=self.blur_module_var, width=60).grid(row=0, column=1, sticky=(tk.W, tk.E), pady=2, padx=(5, 0))
        ttk.Button(blur_frame, text="파일 선택", command=self.browse_blur_module).grid(row=0, column=2, sticky=tk.W, pady=2, padx=(5, 0))
        
        # 블러 활성화 체크박스
        self.blur_enabled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(blur_frame, text="🎯 블러 처리 활성화", variable=self.blur_enabled_var, command=self.on_blur_checkbox_change).grid(row=1, column=0, sticky=tk.W, pady=2)
        
        # 고성능 모드 체크박스
        self.high_performance_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(blur_frame, text="⚡ 고성능 모드 (모든 오버헤드 제거)", variable=self.high_performance_var, command=self.on_performance_checkbox_change).grid(row=2, column=0, sticky=tk.W, pady=2)
        
        blur_info = ttk.Label(blur_frame, 
                             text="※ apply_blur(frame) 함수가 있는 Python 파일을 선택하세요. 없으면 기본 블러 처리됩니다.", 
                             font=("TkDefaultFont", 8), foreground="blue")
        blur_info.grid(row=3, column=0, columnspan=3, sticky=tk.W, pady=(5, 0))

        # 📍 오버레이 설정 프레임 -----------------------------------------
        overlay_frame = ttk.LabelFrame(
            self.main_frame,
            text="📍 영상 오버레이 설정",
            padding="5"
        )
        overlay_frame.grid(
            row=2, column=0, columnspan=4,
            sticky=(tk.W, tk.E),
            pady=(0, 5)
        )
        overlay_frame.columnconfigure(1, weight=1)
        overlay_frame.columnconfigure(3, weight=1)
        
        self.overlay_enabled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(overlay_frame, text="📍 오버레이 활성화", variable=self.overlay_enabled_var, command=self.on_overlay_checkbox_change).grid(row=0, column=0, sticky=tk.W, pady=2, columnspan=4)
        
        ttk.Label(overlay_frame, text="위도 (Latitude):").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.latitude_var = tk.DoubleVar(value=37.5665)  # 서울 기본값
        ttk.Entry(overlay_frame, textvariable=self.latitude_var, width=15).grid(row=1, column=1, sticky=tk.W, pady=2, padx=(5, 0))
        
        ttk.Label(overlay_frame, text="경도 (Longitude):").grid(row=1, column=2, sticky=tk.W, pady=2, padx=(20, 0))
        self.longitude_var = tk.DoubleVar(value=126.9780)  # 서울 기본값
        ttk.Entry(overlay_frame, textvariable=self.longitude_var, width=15).grid(row=1, column=3, sticky=tk.W, pady=2, padx=(5, 0))
        
        overlay_info = ttk.Label(overlay_frame, 
                               text="※ 영상 왼쪽 상단에 프레임 번호, GPS 좌표, 현재 시간, 쓰레드 정보가 표시됩니다.", 
                               font=("TkDefaultFont", 8), foreground="blue")
        overlay_info.grid(row=2, column=0, columnspan=4, sticky=tk.W, pady=(5, 0))

        # 💾 저장 설정 프레임 -----------------------------------------
        save_frame = ttk.LabelFrame(
            self.main_frame,
            text="💾 영상 저장 설정",
            padding="5"
        )
        save_frame.grid(
            row=3, column=0, columnspan=4,
            sticky=(tk.W, tk.E),
            pady=(0, 5)
        )
        save_frame.columnconfigure(1, weight=1)
        
        # 저장 활성화 체크박스
        self.save_enabled_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(save_frame, text="영상 저장 활성화", variable=self.save_enabled_var).grid(row=0, column=0, columnspan=4, sticky=tk.W, pady=(0, 5))
        
        # 저장 경로 설정
        ttk.Label(save_frame, text="저장 경로:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.save_path_var = tk.StringVar(value="./output")
        ttk.Entry(save_frame, textvariable=self.save_path_var, width=60).grid(row=1, column=1, sticky=(tk.W, tk.E), pady=2, padx=(5, 0))
        ttk.Button(save_frame, text="폴더 선택", command=self.browse_save_path).grid(row=1, column=2, sticky=tk.W, pady=2, padx=(5, 0))
        ttk.Button(save_frame, text="폴더 열기", command=self.open_save_folder).grid(row=1, column=3, sticky=tk.W, pady=2, padx=(5, 0))
        
        # 저장 간격 설정 (초 단위)
        ttk.Label(save_frame, text="저장 간격 (초):").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.save_interval_seconds_var = tk.IntVar(value=20)
        ttk.Entry(save_frame, textvariable=self.save_interval_seconds_var, width=15).grid(row=2, column=1, sticky=tk.W, pady=2, padx=(5, 0))
        
        save_info = ttk.Label(save_frame, 
                             text="※ 저장 간격: 각 영상 파일의 길이를 초 단위로 설정 (예: 20초 = 300프레임@15FPS)", 
                             font=("TkDefaultFont", 8), foreground="blue")
        save_info.grid(row=3, column=0, columnspan=4, sticky=tk.W, pady=(5, 0))

        # 🎬 코덱 설정 컨테이너 프레임 ------------------------------------
        codec_container = ttk.Frame(self.main_frame)
        codec_container.grid(row=4, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=(0, 5))
        codec_container.columnconfigure(0, weight=2)  # 코덱 설정이 더 넓게
        codec_container.columnconfigure(1, weight=1)  # 상태 정보

        # 🎬 확장된 압축 코덱 설정 프레임
        codec_frame = ttk.LabelFrame(
            codec_container,
            text="🎬 확장된 압축 코덱 설정 (코덱·컨테이너 선택)",
            padding="5"
        )
        codec_frame.grid(
            row=0, column=0,
            sticky=(tk.W, tk.E, tk.N, tk.S),
            padx=(0, 5)
        )
        # 내부 0~6 컬럼을 확장해 콤보박스가 잘리지 않도록 함
        for c in range(7):
            codec_frame.columnconfigure(c, weight=1)

        # ── 1행: 컨테이너 & 비디오 코덱 ─────────────────────
        ttk.Label(codec_frame, text="컨테이너:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.container_format_var = tk.StringVar(value="mp4")
        container_combo = ttk.Combobox(
            codec_frame, textvariable=self.container_format_var,
            values=["mp4", "mkv", "webm", "avi"],
            width=10,
            state="readonly"
        )
        container_combo.grid(row=0, column=1, sticky=tk.W, pady=2, padx=(5, 0))

        ttk.Label(codec_frame, text="비디오 코덱:").grid(row=0, column=2, sticky=tk.W, pady=2, padx=(20, 0))
        self.video_codec_var = tk.StringVar(value="libx264")
        video_codec_combo = ttk.Combobox(
            codec_frame, textvariable=self.video_codec_var,
            values=["libx264", "libx265", "libvpx-vp9", "libaom-av1", "libxvid", "libx262"],
            width=14,
            state="readonly"
        )
        video_codec_combo.grid(row=0, column=3, sticky=tk.W, pady=2, padx=(5, 0))

        ttk.Label(codec_frame, text="압축 레벨:").grid(row=0, column=4, sticky=tk.W, pady=2, padx=(20, 0))
        self.compression_level_var = tk.IntVar(value=6)
        compression_scale = ttk.Scale(codec_frame, from_=0, to=9, orient=tk.HORIZONTAL,
                                       variable=self.compression_level_var, length=100)
        compression_scale.grid(row=0, column=5, sticky=tk.W, pady=2, padx=(5, 0))
        self.compression_label = ttk.Label(codec_frame, text="6")
        self.compression_label.grid(row=0, column=6, sticky=tk.W, pady=2, padx=(5, 0))
        compression_scale.configure(command=self.update_compression_label)

        # ── 2행: 품질 모드 & 비트레이트 ────────────────────
        ttk.Label(codec_frame, text="품질 모드:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.quality_mode_var = tk.StringVar(value="crf")
        quality_combo = ttk.Combobox(
            codec_frame, textvariable=self.quality_mode_var,
            values=["crf", "cbr", "vbr"],
            width=10,
            state="readonly"
        )
        quality_combo.grid(row=1, column=1, sticky=tk.W, pady=2, padx=(5, 0))

        ttk.Label(codec_frame, text="비트레이트:").grid(row=1, column=2, sticky=tk.W, pady=2, padx=(20, 0))
        self.bitrate_var = tk.StringVar(value="2M")
        ttk.Entry(codec_frame, textvariable=self.bitrate_var, width=10).grid(row=1, column=3, sticky=tk.W, pady=2, padx=(5, 0))

        ttk.Label(codec_frame, text="최대 비트레이트:").grid(row=1, column=4, sticky=tk.W, pady=2, padx=(20, 0))
        self.max_bitrate_var = tk.StringVar(value="4M")
        ttk.Entry(codec_frame, textvariable=self.max_bitrate_var, width=10).grid(row=1, column=5, sticky=tk.W, pady=2, padx=(5, 0))

        # ── 3행: 고급 설정 ──────────────────────────────────
        ttk.Label(codec_frame, text="프리셋:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.preset_var = tk.StringVar(value="fast")
        preset_combo = ttk.Combobox(
            codec_frame, textvariable=self.preset_var,
            values=["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"],
            width=12,
            state="readonly"
        )
        preset_combo.grid(row=2, column=1, sticky=tk.W, pady=2, padx=(5, 0))

        ttk.Label(codec_frame, text="튜닝:").grid(row=2, column=2, sticky=tk.W, pady=2, padx=(20, 0))
        self.tune_var = tk.StringVar(value="none")
        tune_combo = ttk.Combobox(
            codec_frame, textvariable=self.tune_var,
            values=["none", "film", "animation", "grain", "stillimage", "psnr", "ssim", "fastdecode", "zerolatency"],
            width=12,
            state="readonly"
        )
        tune_combo.grid(row=2, column=3, sticky=tk.W, pady=2, padx=(5, 0))

        ttk.Label(codec_frame, text="프로파일:").grid(row=2, column=4, sticky=tk.W, pady=2, padx=(20, 0))
        self.profile_var = tk.StringVar(value="main")
        profile_combo = ttk.Combobox(
            codec_frame, textvariable=self.profile_var,
            values=["baseline", "main", "high", "main10", "main444-8"],
            width=12,
            state="readonly"
        )
        profile_combo.grid(row=2, column=5, sticky=tk.W, pady=2, padx=(5, 0))

        # ── 4행: 하드웨어 가속 & 픽셀 포맷 ────────────────────
        ttk.Label(codec_frame, text="하드웨어 가속:").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.hardware_accel_var = tk.StringVar(value="none")
        hw_combo = ttk.Combobox(
            codec_frame, textvariable=self.hardware_accel_var,
            values=["none", "nvidia", "intel", "amd"],
            width=10,
            state="readonly"
        )
        hw_combo.grid(row=3, column=1, sticky=tk.W, pady=2, padx=(5, 0))

        ttk.Label(codec_frame, text="픽셀 포맷:").grid(row=3, column=2, sticky=tk.W, pady=2, padx=(20, 0))
        self.pixel_format_var = tk.StringVar(value="yuv420p")
        pixel_combo = ttk.Combobox(
            codec_frame, textvariable=self.pixel_format_var,
            values=["yuv420p", "yuv422p", "yuv444p", "yuv420p10le"],
            width=12,
            state="readonly"
        )
        pixel_combo.grid(row=3, column=3, sticky=tk.W, pady=2, padx=(5, 0))

        ttk.Label(codec_frame, text="키프레임 간격:").grid(row=3, column=4, sticky=tk.W, pady=2, padx=(20, 0))
        self.keyframe_interval_var = tk.IntVar(value=250)
        ttk.Entry(codec_frame, textvariable=self.keyframe_interval_var, width=10).grid(row=3, column=5, sticky=tk.W, pady=2, padx=(5, 0))

        # ── 5행: 추가 옵션 ────────────────────────────────────
        ttk.Label(codec_frame, text="추가 옵션:").grid(row=4, column=0, sticky=tk.W, pady=2)
        self.extra_options_var = tk.StringVar()
        ttk.Entry(codec_frame, textvariable=self.extra_options_var, width=60).grid(row=4, column=1, columnspan=5, sticky=(tk.W, tk.E), pady=2, padx=(5, 0))
        
        # 코덱 설명 라벨
        codec_info = ttk.Label(codec_frame, 
                             text="※ 압축 레벨: 0=빠름/큰파일, 9=느림/작은파일 | 품질 모드: CRF=일정품질, CBR=일정비트레이트, VBR=가변비트레이트", 
                             font=("TkDefaultFont", 8), foreground="blue")
        codec_info.grid(row=5, column=0, columnspan=6, sticky=tk.W, pady=(5, 0))
        
        # ⚙️ 기타 설정, FPS 설정, 큐 설정 통합 프레임 -----------------------
        settings_container = ttk.Frame(self.main_frame)
        settings_container.grid(row=5, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=(0, 5))
        settings_container.columnconfigure(0, weight=1)
        settings_container.columnconfigure(1, weight=1)
        settings_container.columnconfigure(2, weight=1)

        # ⚙️ 기타 설정 프레임
        misc_frame = ttk.LabelFrame(settings_container, text="⚙️ 기타 설정", padding="5")
        misc_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 3))
        misc_frame.columnconfigure(1, weight=1)
        
        ttk.Label(misc_frame, text="쓰레드 수:").grid(row=0, column=0, sticky=tk.W, pady=1)
        self.thread_count_var = tk.IntVar(value=get_env_value('DEFAULT_THREAD_COUNT', 6, int))
        ttk.Entry(misc_frame, textvariable=self.thread_count_var, width=8).grid(row=0, column=1, sticky=(tk.W, tk.E), pady=1, padx=(5, 0))
        
        ttk.Label(misc_frame, text="최대 시간(초):").grid(row=1, column=0, sticky=tk.W, pady=1)
        self.max_duration_var = tk.StringVar()
        ttk.Entry(misc_frame, textvariable=self.max_duration_var, width=8).grid(row=1, column=1, sticky=(tk.W, tk.E), pady=1, padx=(5, 0))
        
        ttk.Label(misc_frame, text="로스율(%):").grid(row=2, column=0, sticky=tk.W, pady=1)
        self.frame_loss_var = tk.DoubleVar(value=0.0)
        ttk.Entry(misc_frame, textvariable=self.frame_loss_var, width=8).grid(row=2, column=1, sticky=(tk.W, tk.E), pady=1, padx=(5, 0))
        
        ttk.Label(misc_frame, text="재연결 간격(초):").grid(row=3, column=0, sticky=tk.W, pady=1)
        self.reconnect_var = tk.IntVar(value=5)
        ttk.Entry(misc_frame, textvariable=self.reconnect_var, width=8).grid(row=3, column=1, sticky=(tk.W, tk.E), pady=1, padx=(5, 0))
        
        self.processing_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(misc_frame, text="영상 처리 활성화", variable=self.processing_var).grid(row=4, column=0, columnspan=2, sticky=tk.W, pady=1)

        # 📊 FPS 설정 프레임
        fps_frame = ttk.LabelFrame(settings_container, text="📊 FPS 설정", padding="5")
        fps_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(3, 3))
        fps_frame.columnconfigure(1, weight=1)
        
        ttk.Label(fps_frame, text="입력 FPS:").grid(row=0, column=0, sticky=tk.W, pady=1)
        self.input_fps_var = tk.DoubleVar(value=get_env_value('DEFAULT_INPUT_FPS', 15.0, float))
        ttk.Entry(fps_frame, textvariable=self.input_fps_var, width=8).grid(row=0, column=1, sticky=(tk.W, tk.E), pady=1, padx=(5, 0))
        
        self.force_fps_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(fps_frame, text="FPS 강제 설정", variable=self.force_fps_var).grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=1)

        # 🔧 큐 설정 프레임
        queue_frame = ttk.LabelFrame(settings_container, text="🔧 큐 설정", padding="5")
        queue_frame.grid(row=0, column=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(3, 0))
        queue_frame.columnconfigure(1, weight=1)
        
        ttk.Label(queue_frame, text="처리 큐 크기:").grid(row=0, column=0, sticky=tk.W, pady=1)
        self.processing_queue_size_var = tk.IntVar(value=1000)
        ttk.Entry(queue_frame, textvariable=self.processing_queue_size_var, width=8).grid(row=0, column=1, sticky=(tk.W, tk.E), pady=1, padx=(5, 0))
        
        ttk.Label(queue_frame, text="미리보기 큐 크기:").grid(row=1, column=0, sticky=tk.W, pady=1)
        self.preview_queue_size_var = tk.IntVar(value=50)
        ttk.Entry(queue_frame, textvariable=self.preview_queue_size_var, width=8).grid(row=1, column=1, sticky=(tk.W, tk.E), pady=1, padx=(5, 0))

        # 📊 현재 코덱 설정 상태 프레임 (코덱 설정 옆에 배치)
        codec_status_frame = ttk.LabelFrame(
            codec_container,
            text="📊 현재 코덱 설정",
            padding="5"
        )
        codec_status_frame.grid(
            row=0, column=1,
            sticky=(tk.W, tk.E, tk.N, tk.S),
            padx=(5, 0)
        )
        codec_status_frame.columnconfigure(1, weight=1)
        
        # 코덱 상태 라벨들
        self.codec_status_labels = {}
        codec_status_items = [
            ('current_codec', '현재 코덱:'),
            ('compression_info', '압축 정보:'),
            ('quality_info', '품질 설정:'),
            ('performance_info', '성능 예상:'),
            ('file_size_estimate', '파일 크기:'),
            ('encoding_status', '인코딩 상태:')
        ]
        
        for i, (key, label) in enumerate(codec_status_items):
            ttk.Label(codec_status_frame, text=label, font=("TkDefaultFont", 8)).grid(row=i, column=0, sticky=tk.W, pady=1)
            self.codec_status_labels[key] = ttk.Label(codec_status_frame, text="설정되지 않음", foreground="gray", font=("TkDefaultFont", 8))
            self.codec_status_labels[key].grid(row=i, column=1, sticky=(tk.W, tk.E), pady=1, padx=(5, 0))
        
        # 코덱 설정 변경 감지를 위한 바인딩
        self.video_codec_var.trace('w', self.update_codec_status)
        self.compression_level_var.trace('w', self.update_codec_status)
        self.quality_mode_var.trace('w', self.update_codec_status)
        self.bitrate_var.trace('w', self.update_codec_status)
        self.preset_var.trace('w', self.update_codec_status)
        self.container_format_var.trace('w', self.update_codec_status)
        self.hardware_accel_var.trace('w', self.update_codec_status)
        self.tune_var.trace('w', self.update_codec_status)
        self.profile_var.trace('w', self.update_codec_status)
        
        # 🎮 컨트롤 버튼 프레임 ---------------------------------------
        button_frame = ttk.Frame(self.main_frame)
        button_frame.grid(row=6, column=0, columnspan=4, pady=(0, 5))
        
        self.start_button = ttk.Button(button_frame, text="시작", command=self.start_processor)
        self.start_button.pack(side=tk.LEFT, padx=(0, 5))
        
        self.stop_button = ttk.Button(button_frame, text="중지", command=self.stop_processor, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=(0, 5))
        
        self.reset_button = ttk.Button(button_frame, text="통계 초기화", command=self.reset_statistics)
        self.reset_button.pack(side=tk.LEFT, padx=(0, 5))
        
        # FFmpeg 체크 버튼
        self.check_ffmpeg_button = ttk.Button(button_frame, text="FFmpeg 확인", command=self.check_ffmpeg)
        self.check_ffmpeg_button.pack(side=tk.LEFT, padx=(0, 5))
        
        # 코덱 정보 버튼
        self.codec_info_button = ttk.Button(button_frame, text="코덱 정보", command=self.show_codec_info)
        self.codec_info_button.pack(side=tk.LEFT, padx=(0, 5))
        
        # 🆕 성능 프로파일 저장 버튼
        self.save_profile_button = ttk.Button(button_frame, text="📊 성능 보고서 저장", command=self.save_performance_report)
        self.save_profile_button.pack(side=tk.LEFT, padx=(0, 5))
        
        # 실시간 미리보기 토글 버튼
        self.preview_toggle_button = ttk.Button(button_frame, text="📺 미리보기 끄기", command=self.toggle_preview)
        self.preview_toggle_button.pack(side=tk.LEFT, padx=(0, 5))
        
        # 블러 처리 토글 버튼
        self.blur_toggle_button = ttk.Button(button_frame, text="🎯 블러 끄기", command=self.toggle_blur)
        self.blur_toggle_button.pack(side=tk.LEFT, padx=(0, 5))
        
        # 고성능 모드 토글 버튼
        self.performance_toggle_button = ttk.Button(button_frame, text="⚡ 고성능 켜기", command=self.toggle_performance)
        self.performance_toggle_button.pack(side=tk.LEFT, padx=(0, 5))
        
        # 오버레이 토글 버튼
        self.overlay_toggle_button = ttk.Button(button_frame, text="📍 오버레이 끄기", command=self.toggle_overlay)
        self.overlay_toggle_button.pack(side=tk.LEFT, padx=(0, 5))
        
        # 📺 실시간 미리보기 및 통계 프레임 ----------------------------
        preview_stats_frame = ttk.Frame(self.main_frame)
        preview_stats_frame.grid(row=7, column=0, columnspan=4, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 5))
        preview_stats_frame.columnconfigure(0, weight=2)  # 미리보기 영역 2배 크기
        preview_stats_frame.columnconfigure(1, weight=1)  # 통계 영역
        preview_stats_frame.rowconfigure(0, weight=1)
        
        # 미리보기 프레임 (왼쪽)
        preview_frame = ttk.LabelFrame(preview_stats_frame, text="📺 실시간 미리보기", padding="10")
        preview_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5))
        
        # 스크롤 가능한 미리보기 프레임
        preview_canvas = tk.Canvas(preview_frame, height=450)
        preview_scrollbar = ttk.Scrollbar(preview_frame, orient="vertical", command=preview_canvas.yview)
        self.preview_scrollable_frame = ttk.Frame(preview_canvas)
        
        self.preview_scrollable_frame.bind(
            "<Configure>",
            lambda e: preview_canvas.configure(scrollregion=preview_canvas.bbox("all"))
        )
        
        preview_canvas.create_window((0, 0), window=self.preview_scrollable_frame, anchor="nw")
        preview_canvas.configure(yscrollcommand=preview_scrollbar.set)
        
        preview_canvas.pack(side="left", fill="both", expand=True)
        preview_scrollbar.pack(side="right", fill="y")
        
        self.preview_labels = {}
        
        # 통계 프레임 (오른쪽)
        stats_container_frame = ttk.Frame(preview_stats_frame)
        stats_container_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 0))
        stats_container_frame.columnconfigure(0, weight=1)
        stats_container_frame.rowconfigure(0, weight=1)
        stats_container_frame.rowconfigure(1, weight=1)
        
        # 전체 통계 프레임
        stats_frame = ttk.LabelFrame(stats_container_frame, text="📊 전체 통계", padding="10")
        stats_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 5))
        
        # 통계 라벨들
        self.stats_labels = {}
        stats_items = [
            ('received_frames', '수신된 프레임'),
            ('processed_frames', '처리된 프레임'),
            ('saved_frames', '저장된 프레임'),
            ('lost_frames', '손실된 프레임'),
            ('error_frames', '오류 프레임'),
            ('loss_rate', '프레임 로스율 (%)'),
            ('processing_rate', '처리 성공률 (%)'),
            ('save_rate', '저장 성공률 (%)'),
            ('processing_fps', '초당 처리 프레임수'),
            ('thread_count', '쓰레드 수'),
            ('queue_size', '큐 크기'),
            ('runtime', '실행 시간 (초)'),
            ('current_codec_info', '현재 코덱'),
            ('encoding_performance', '인코딩 성능'),
            ('file_format', '파일 포맷')
        ]
        
        for i, (key, label) in enumerate(stats_items):
            ttk.Label(stats_frame, text=f"{label}:").grid(row=i, column=0, sticky=tk.W, pady=1)
            self.stats_labels[key] = ttk.Label(stats_frame, text="0" if key not in ['current_codec_info', 'encoding_performance', 'file_format', 'processing_fps'] else "대기 중")
            self.stats_labels[key].grid(row=i, column=1, sticky=tk.W, pady=1, padx=(10, 0))
        
        # 실시간 코덱 성능 정보 프레임
        codec_perf_frame = ttk.LabelFrame(stats_container_frame, text="⚡ 코덱 성능 정보", padding="10")
        codec_perf_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(5, 0))
        
        # 코덱 성능 라벨들
        self.codec_perf_labels = {}
        codec_perf_items = [
            ('encoding_speed', '인코딩 속도:'),
            ('compression_ratio', '압축 비율:'),
            ('avg_bitrate', '평균 비트레이트:'),
            ('current_fps', '현재 FPS:'),
            ('estimated_size', '예상 파일 크기:')
        ]
        
        for i, (key, label) in enumerate(codec_perf_items):
            ttk.Label(codec_perf_frame, text=label).grid(row=i, column=0, sticky=tk.W, pady=2)
            self.codec_perf_labels[key] = ttk.Label(codec_perf_frame, text="대기 중...", foreground="gray")
            self.codec_perf_labels[key].grid(row=i, column=1, sticky=tk.W, pady=2, padx=(10, 0))
        
        # 🆕 리소스 모니터링 프레임
        resource_frame = ttk.LabelFrame(stats_container_frame, text="💻 리소스 모니터링", padding="10")
        resource_frame.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(5, 0))
        
        # 리소스 모니터링 라벨들 (가용 자원 대비 사용률 중심)
        self.resource_labels = {}
        resource_items = [
            ('cpu_usage', 'CPU 사용률:'),
            ('ram_usage', 'RAM 사용률:'),
            ('gpu_usage', 'GPU 사용률:'),
            ('gpu_memory', 'GPU 메모리:')
        ]
        
        for i, (key, label) in enumerate(resource_items):
            ttk.Label(resource_frame, text=label).grid(row=i, column=0, sticky=tk.W, pady=2)
            self.resource_labels[key] = ttk.Label(resource_frame, text="대기 중...", foreground="gray")
            self.resource_labels[key].grid(row=i, column=1, sticky=tk.W, pady=2, padx=(10, 0))
        
        # 🆕 성능 프로파일링 프레임
        performance_frame = ttk.LabelFrame(stats_container_frame, text="⏱️ 성능 프로파일", padding="10")
        performance_frame.grid(row=3, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(5, 0))
        
        # 성능 프로파일링 라벨들
        self.performance_labels = {}
        performance_items = [
            ('frame_processing_avg', '프레임 처리 (평균):'),
            ('blur_processing_avg', '블러 처리 (평균):'),
            ('overlay_processing_avg', '오버레이 (평균):'),
            ('save_processing_avg', '저장 처리 (평균):'),
            ('total_processing_time', '총 처리 시간:')
        ]
        
        for i, (key, label) in enumerate(performance_items):
            ttk.Label(performance_frame, text=label).grid(row=i, column=0, sticky=tk.W, pady=2)
            self.performance_labels[key] = ttk.Label(performance_frame, text="대기 중...", foreground="gray")
            self.performance_labels[key].grid(row=i, column=1, sticky=tk.W, pady=2, padx=(10, 0))
        
        # 통계 컨테이너 프레임의 rowconfigure 업데이트
        stats_container_frame.rowconfigure(2, weight=1)
        stats_container_frame.rowconfigure(3, weight=1)
        
        # 📝 로그 프레임 -----------------------------------------------
        log_frame = ttk.LabelFrame(self.main_frame, text="📝 로그", padding="5")
        log_frame.grid(row=8, column=0, columnspan=4, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 5))
        
        self.log_text = tk.Text(log_frame, height=8, width=80)
        log_scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 메인 프레임 그리드 설정
        self.main_frame.columnconfigure(0, weight=1)
        self.main_frame.rowconfigure(7, weight=1)  # 미리보기/통계 프레임 확장
        self.main_frame.rowconfigure(8, weight=1)  # 로그 프레임 확장
        
        self.start_time = None
        
        # 초기 코덱 상태 업데이트
        self.update_codec_status()
    
    def update_codec_status(self, *args):
        """코덱 설정 상태 실시간 업데이트"""
        try:
            # 현재 설정값 가져오기
            codec = self.video_codec_var.get()
            compression = self.compression_level_var.get()
            quality_mode = self.quality_mode_var.get()
            bitrate = self.bitrate_var.get()
            preset = self.preset_var.get()
            container = self.container_format_var.get()
            hw_accel = self.hardware_accel_var.get()
            tune = self.tune_var.get()
            profile = self.profile_var.get()
            
            # 코덱 정보 매핑
            codec_info = {
                'libx264': {'name': 'H.264/AVC', 'desc': '범용 고성능', 'color': 'blue'},
                'libx265': {'name': 'H.265/HEVC', 'desc': '고효율 압축', 'color': 'green'},
                'libvpx-vp9': {'name': 'VP9', 'desc': '웹 최적화', 'color': 'purple'},
                'libaom-av1': {'name': 'AV1', 'desc': '차세대 코덱', 'color': 'red'},
                'libxvid': {'name': 'Xvid', 'desc': '호환성 우선', 'color': 'orange'},
                'libx262': {'name': 'H.262/MPEG-2', 'desc': '방송용', 'color': 'brown'}
            }
            
            # 품질 모드 설명
            quality_desc = {
                'crf': 'CRF (일정 품질)',
                'cbr': 'CBR (일정 비트레이트)',
                'vbr': 'VBR (가변 비트레이트)'
            }
            
            # 압축 레벨 설명
            compression_desc = {
                0: '최고속 (큰 파일)', 1: '매우 빠름', 2: '빠름',
                3: '보통빠름', 4: '보통', 5: '보통느림',
                6: '느림 (권장)', 7: '매우 느림', 8: '극도로 느림',
                9: '최고압축 (작은 파일)'
            }
            
            # 성능 예상 정보
            performance_info = self.get_performance_info(codec, compression, preset, hw_accel)
            
            # 파일 크기 예상
            size_info = self.get_size_estimate(codec, compression, quality_mode, bitrate)
            
            # 현재 코덱 정보 업데이트
            current_codec_info = codec_info.get(codec, {'name': codec, 'desc': '알 수 없음', 'color': 'black'})
            codec_text = f"{current_codec_info['name']} ({current_codec_info['desc']})"
            if hw_accel != 'none':
                codec_text += f" + {hw_accel.upper()}"
            
            self.codec_status_labels['current_codec'].config(
                text=codec_text, 
                foreground=current_codec_info['color']
            )
            
            # 압축 정보 업데이트
            compression_text = f"레벨 {compression} - {compression_desc.get(compression, '알 수 없음')}"
            color = 'darkgreen' if compression >= 6 else 'orange' if compression >= 3 else 'red'
            self.codec_status_labels['compression_info'].config(text=compression_text, foreground=color)
            
            # 품질 설정 업데이트
            quality_text = f"{quality_desc.get(quality_mode, quality_mode)} - {bitrate}"
            if profile != 'main':
                quality_text += f" ({profile})"
            self.codec_status_labels['quality_info'].config(text=quality_text, foreground='blue')
            
            # 성능 정보 업데이트
            perf_text, perf_color = performance_info
            self.codec_status_labels['performance_info'].config(text=perf_text, foreground=perf_color)
            
            # 파일 크기 예상 업데이트
            size_text, size_color = size_info
            self.codec_status_labels['file_size_estimate'].config(text=size_text, foreground=size_color)
            
            # 인코딩 상태 업데이트
            if self.running:
                status_text = f"🔴 인코딩 중 ({container.upper()})"
                status_color = 'red'
            else:
                status_text = f"⚪ 대기 중 ({container.upper()})"
                status_color = 'gray'
            self.codec_status_labels['encoding_status'].config(text=status_text, foreground=status_color)
            
            # 🎬 코덱 설정 변경 시 로그 출력 (스로틀링 적용)
            if not hasattr(self, '_last_codec_log_time'):
                self._last_codec_log_time = 0
            
            current_time = time.time()
            # 2초마다 한 번씩만 로그 출력 (너무 자주 출력되지 않도록)
            if current_time - self._last_codec_log_time > 2.0:
                codec_summary = f"🎬 코덱 설정: {codec} | 레벨 {compression} | {quality_mode.upper()} | {bitrate} | {container.upper()}"
                if hw_accel != 'none':
                    codec_summary += f" | {hw_accel.upper()}"
                
                # 실행 중이 아닐 때만 로그 출력 (실행 중에는 너무 많이 출력됨)
                if not self.running:
                    self.log_message(codec_summary)
                
                self._last_codec_log_time = current_time
            
        except Exception as e:
            # 오류 발생 시 기본값 표시
            for key in self.codec_status_labels:
                self.codec_status_labels[key].config(text="설정 오류", foreground="red")
    
    def get_performance_info(self, codec, compression, preset, hw_accel):
        """성능 정보 계산"""
        # 하드웨어 가속 보너스
        hw_bonus = 3 if hw_accel != 'none' else 0
        
        # 코덱별 기본 성능 점수 (0-10)
        codec_scores = {
            'libx264': 8, 'libx265': 5, 'libvpx-vp9': 6,
            'libaom-av1': 3, 'libxvid': 9, 'libx262': 7
        }
        
        # 프리셋별 성능 점수
        preset_scores = {
            'ultrafast': 10, 'superfast': 9, 'veryfast': 8, 'faster': 7,
            'fast': 6, 'medium': 5, 'slow': 4, 'slower': 3, 'veryslow': 2
        }
        
        base_score = codec_scores.get(codec, 5)
        preset_score = preset_scores.get(preset, 5)
        compression_penalty = compression  # 압축 레벨이 높을수록 느려짐
        
        total_score = base_score + preset_score - compression_penalty + hw_bonus
        
        if total_score >= 12:
            return "🟢 실시간 처리 가능", "green"
        elif total_score >= 8:
            return "🟡 준실시간 처리", "orange"
        elif total_score >= 5:
            return "🟠 느린 처리", "darkorange"
        else:
            return "🔴 매우 느린 처리", "red"
    
    def get_size_estimate(self, codec, compression, quality_mode, bitrate):
        """파일 크기 예상 계산"""
        # 코덱별 압축 효율 (숫자가 낮을수록 더 압축됨)
        codec_efficiency = {
            'libx264': 1.0, 'libx265': 0.5, 'libvpx-vp9': 0.65,
            'libaom-av1': 0.4, 'libxvid': 1.2, 'libx262': 1.5
        }
        
        # 기본 크기 계산 (1분 1080p 기준)
        base_size = 100  # MB
        
        # 코덱 효율 적용
        codec_mult = codec_efficiency.get(codec, 1.0)
        
        # 압축 레벨 적용 (레벨이 높을수록 더 압축)
        compression_mult = 1.0 - (compression * 0.08)  # 8%씩 감소
        
        # 비트레이트 적용
        try:
            bitrate_value = float(bitrate.replace('M', '').replace('K', ''))
            if 'K' in bitrate:
                bitrate_value /= 1000
            bitrate_mult = bitrate_value / 2.0  # 2M 기준
        except:
            bitrate_mult = 1.0
        
        # 최종 크기 계산
        final_size = base_size * codec_mult * compression_mult * bitrate_mult
        
        # 색상 결정
        if final_size < 20:
            color = "green"
        elif final_size < 50:
            color = "blue"
        elif final_size < 80:
            color = "orange"
        else:
            color = "red"
        
        return f"{final_size:.1f}MB (1분 1080p 기준)", color
    
    def update_compression_label(self, value):
        """압축 레벨 라벨 업데이트"""
        level = int(float(value))
        self.compression_label.config(text=str(level))
    
    def check_ffmpeg(self):
        """FFmpeg 설치 확인"""
        try:
            result = subprocess.run(['ffmpeg', '-version'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                # 버전 정보 추출
                version_line = result.stdout.split('\n')[0]
                self.log_message(f"✅ FFmpeg 설치됨: {version_line}")
                messagebox.showinfo("FFmpeg 확인", f"FFmpeg가 설치되어 있습니다!\n\n{version_line}")
            else:
                self.log_message("❌ FFmpeg 설치 안됨")
                messagebox.showerror("FFmpeg 확인", "FFmpeg가 설치되지 않았습니다.")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            self.log_message("❌ FFmpeg 설치 안됨")
            messagebox.showerror("FFmpeg 확인", 
                               "FFmpeg가 설치되지 않았습니다.\n\n" +
                               "설치 방법:\n" +
                               "1. Windows: https://ffmpeg.org/download.html\n" +
                               "2. macOS: brew install ffmpeg\n" +
                               "3. Ubuntu: sudo apt install ffmpeg")
    
    def show_codec_info(self):
        """코덱 정보 표시"""
        info_text = """
🎬 비디오 코덱 정보

📊 H.264 (libx264)
- 가장 널리 사용되는 코덱
- 모든 기기에서 재생 가능
- 균형 잡힌 성능과 품질
- 실시간 인코딩에 적합

📊 H.265 (libx265)
- H.264 대비 50% 더 효율적
- 같은 화질에서 파일 크기 절반
- 인코딩 시간 더 오래 걸림
- 최신 기기에서 지원

📊 VP9 (libvpx-vp9)
- 구글 개발 오픈소스 코덱
- 웹 스트리밍에 최적화
- YouTube에서 사용
- 로열티 없음

📊 AV1 (libaom-av1)
- 차세대 오픈소스 코덱
- VP9 대비 30% 더 효율적
- 매우 느린 인코딩
- 최신 브라우저에서 지원

⚙️ 압축 레벨 가이드
0-2: 빠른 인코딩, 큰 파일
3-5: 균형 잡힌 설정
6-7: 좋은 압축률 (권장)
8-9: 최고 압축률, 매우 느림

🎯 품질 모드 설명
CRF: 일정한 품질 (권장)
CBR: 일정한 비트레이트 (스트리밍용)
VBR: 가변 비트레이트 (효율적)
        """
        messagebox.showinfo("코덱 정보", info_text)
    
    def save_performance_report(self):
        """성능 보고서 저장"""
        try:
            # 파일 저장 대화상자
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            default_filename = f"performance_report_{timestamp}.json"
            
            filepath = filedialog.asksaveasfilename(
                title="성능 보고서 저장",
                defaultextension=".json",
                initialfile=default_filename,
                filetypes=[
                    ("JSON 파일", "*.json"),
                    ("모든 파일", "*.*")
                ]
            )
            
            if filepath:
                # 기본 보고서 데이터 구성
                report = {
                    "report_info": {
                        "generated_at": datetime.now().isoformat(),
                        "runtime_seconds": time.time() - self.start_time if self.start_time else 0,
                        "processor_running": self.running,
                        "config": {}
                    },
                    "frame_statistics": {},
                    "resource_summary": {},
                    "performance_profiles": {},
                    "resource_history": {}
                }
                
                # 설정 정보 추가 (안전하게)
                if self.config:
                    try:
                        report["report_info"]["config"] = {
                            "thread_count": getattr(self.config, 'thread_count', 0),
                            "input_fps": getattr(self.config, 'input_fps', 0),
                            "video_codec": getattr(self.config, 'video_codec', "unknown"),
                            "compression_level": getattr(self.config, 'compression_level', 0),
                            "save_enabled": getattr(self.config, 'save_enabled', False),
                            "container_format": getattr(self.config, 'container_format', "unknown"),
                            "quality_mode": getattr(self.config, 'quality_mode', "unknown"),
                            "bitrate": getattr(self.config, 'bitrate', "unknown"),
                            "sources_count": len(getattr(self.config, 'sources', []))
                        }
                    except Exception as e:
                        self.log_message(f"설정 정보 수집 중 오류: {e}")
                        report["report_info"]["config"] = {"error": str(e)}
                
                # 프로세서 통계 추가 (안전하게)
                if self.processor:
                    try:
                        stats = self.processor.get_statistics()
                        report["frame_statistics"] = {
                            "received_frames": stats.get('received_frames', 0),
                            "processed_frames": stats.get('processed_frames', 0),
                            "saved_frames": stats.get('saved_frames', 0),
                            "lost_frames": stats.get('lost_frames', 0),
                            "error_frames": stats.get('error_frames', 0),
                            "loss_rate_percent": stats.get('loss_rate', 0),
                            "processing_rate_percent": stats.get('processing_rate', 0),
                            "save_rate_percent": stats.get('save_rate', 0)
                        }
                        
                        # 성능 프로파일 정보 (상세 데이터 포함)
                        if hasattr(self.processor, 'performance_profiler') and self.processor.performance_profiler:
                            try:
                                # 기본 통계 정보
                                report["performance_profiles"] = stats.get('performance_stats', {})
                                
                                # 상세 프로파일 데이터 추가
                                detailed_profiles = self.processor.performance_profiler.get_profile_stats()
                                report["detailed_performance_profiles"] = detailed_profiles
                                
                            except Exception as e:
                                self.log_message(f"성능 프로파일 수집 중 오류: {e}")
                                report["performance_profiles"] = {"error": str(e)}
                                report["detailed_performance_profiles"] = {"error": str(e)}
                        
                        # 리소스 모니터링 정보
                        if hasattr(self.processor, 'resource_monitor') and self.processor.resource_monitor:
                            try:
                                resource_summary = self.processor.resource_monitor.get_summary_stats()
                                report["resource_summary"] = resource_summary
                                
                                resource_history = self.processor.resource_monitor.get_history()
                                report["resource_history"] = resource_history
                            except Exception as e:
                                self.log_message(f"리소스 정보 수집 중 오류: {e}")
                                report["resource_summary"] = {"error": str(e)}
                                report["resource_history"] = {"error": str(e)}
                        
                    except Exception as e:
                        self.log_message(f"프로세서 통계 수집 중 오류: {e}")
                        report["frame_statistics"] = {"error": str(e)}
                else:
                    report["frame_statistics"] = {"note": "프로세서가 실행되지 않았습니다"}
                    report["performance_profiles"] = {"note": "프로세서가 실행되지 않았습니다"}
                    report["detailed_performance_profiles"] = {"note": "프로세서가 실행되지 않았습니다"}
                    report["resource_summary"] = {"note": "프로세서가 실행되지 않았습니다"}
                    report["resource_history"] = {"note": "프로세서가 실행되지 않았습니다"}
                
                # 통합 보고서 저장 (하나의 파일로)
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(report, f, indent=2, ensure_ascii=False)
                
                self.log_message(f"📊 통합 성능 보고서 저장됨: {os.path.basename(filepath)}")
                
                # 성공 메시지
                messagebox.showinfo("성공", 
                                   f"통합 성능 보고서가 저장되었습니다!\n\n" +
                                   f"파일: {os.path.basename(filepath)}\n\n" +
                                   f"포함 내용:\n" +
                                   f"• 실행 환경 정보\n" +
                                   f"• 프레임 처리 통계\n" +
                                   f"• 상세 성능 프로파일\n" +
                                   f"• 시스템 리소스 사용량\n" +
                                   f"• 시간별 리소스 히스토리")
                
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            self.log_message(f"성능 보고서 저장 실패: {e}")
            self.log_message(f"상세 오류: {error_details}")
            messagebox.showerror("오류", f"성능 보고서 저장 실패:\n{e}")
    
    def update_resource_monitoring(self):
        """리소스 모니터링 정보 업데이트 (가용 자원 대비 사용률 중심)"""
        if not self.processor or not self.running:
            # 대기 상태 표시
            for key in self.resource_labels:
                self.resource_labels[key].config(text="대기 중...", foreground="gray")
            return
        
        try:
            resource_stats = self.processor.resource_monitor.get_current_stats()
            
            if resource_stats['cpu']:
                cpu_data = resource_stats['cpu']
                # 시스템 CPU 사용률 (가용 자원 대비)
                system_cpu = cpu_data['system_cpu']
                cpu_count = cpu_data['cpu_count']
                
                self.resource_labels['cpu_usage'].config(
                    text=f"{system_cpu:.1f}% / 100% (🖥️{cpu_count}코어)",
                    foreground="red" if system_cpu > 90 else "orange" if system_cpu > 70 else "green"
                )
            
            if resource_stats['ram']:
                ram_data = resource_stats['ram']
                # 시스템 RAM 사용률 (가용 자원 대비)
                system_ram_percent = ram_data['system_ram_percent']
                system_ram_used_gb = ram_data['system_ram_used_gb']
                system_ram_total_gb = ram_data['system_ram_total_gb']
                
                self.resource_labels['ram_usage'].config(
                    text=f"{system_ram_percent:.1f}% ({system_ram_used_gb:.1f}/{system_ram_total_gb:.1f}GB)",
                    foreground="red" if system_ram_percent > 90 else "orange" if system_ram_percent > 80 else "green"
                )
            
            # GPU 정보 (가용 자원 대비 사용률)
            if resource_stats['gpu_available'] and resource_stats['gpu']:
                gpu_data = resource_stats['gpu']
                if gpu_data['gpus']:
                    gpu = gpu_data['gpus'][0]  # 첫 번째 GPU 정보 표시
                    gpu_load = gpu['load']
                    gpu_memory_percent = gpu['memory_percent']
                    gpu_memory_used = gpu['memory_used_mb']
                    gpu_memory_total = gpu['memory_total_mb']
                    gpu_temp = gpu['temperature']
                    
                    self.resource_labels['gpu_usage'].config(
                        text=f"{gpu_load:.1f}% / 100% (🌡️{gpu_temp}°C)",
                        foreground="red" if gpu_load > 90 else "orange" if gpu_load > 70 else "green"
                    )
                    self.resource_labels['gpu_memory'].config(
                        text=f"{gpu_memory_percent:.1f}% ({gpu_memory_used:.0f}/{gpu_memory_total:.0f}MB)",
                        foreground="red" if gpu_memory_percent > 90 else "orange" if gpu_memory_percent > 80 else "green"
                    )
                else:
                    self.resource_labels['gpu_usage'].config(text="GPU 없음", foreground="gray")
                    self.resource_labels['gpu_memory'].config(text="GPU 없음", foreground="gray")
            else:
                self.resource_labels['gpu_usage'].config(text="사용 불가", foreground="gray")
                self.resource_labels['gpu_memory'].config(text="사용 불가", foreground="gray")
                
        except Exception as e:
            logger.debug(f"리소스 모니터링 업데이트 오류: {e}")
            for key in self.resource_labels:
                self.resource_labels[key].config(text="오류", foreground="red")
    
    def update_performance_monitoring(self):
        """성능 프로파일링 정보 업데이트"""
        if not self.processor or not self.running:
            # 대기 상태 표시
            for key in self.performance_labels:
                self.performance_labels[key].config(text="대기 중...", foreground="gray")
            return
        
        try:
            performance_stats = self.processor.performance_profiler.get_profile_stats()
            
            if performance_stats['summary']:
                summary = performance_stats['summary']
                
                # 각 처리 단계별 평균 시간
                stages = [
                    ('frame_processing', 'frame_processing_avg'),
                    ('blur_processing', 'blur_processing_avg'),
                    ('overlay_processing', 'overlay_processing_avg'),
                    ('save_processing', 'save_processing_avg')
                ]
                
                for stage_name, label_key in stages:
                    if stage_name in summary:
                        avg_ms = summary[stage_name]['avg_ms']
                        count = summary[stage_name]['count']
                        
                        # 성능에 따른 색상 결정
                        if stage_name == 'frame_processing':
                            color = "green" if avg_ms < 50 else "orange" if avg_ms < 100 else "red"
                        elif stage_name == 'blur_processing':
                            color = "green" if avg_ms < 30 else "orange" if avg_ms < 60 else "red"
                        elif stage_name == 'overlay_processing':
                            color = "green" if avg_ms < 10 else "orange" if avg_ms < 20 else "red"
                        elif stage_name == 'save_processing':
                            color = "green" if avg_ms < 100 else "orange" if avg_ms < 200 else "red"
                        else:
                            color = "blue"
                        
                        self.performance_labels[label_key].config(
                            text=f"{avg_ms:.1f}ms (x{count})",
                            foreground=color
                        )
                    else:
                        self.performance_labels[label_key].config(text="데이터 없음", foreground="gray")
                
                # 총 처리 시간
                if 'total_processing' in summary:
                    total_ms = summary['total_processing']['total_ms']
                    total_sec = total_ms / 1000
                    
                    if total_sec < 60:
                        time_text = f"{total_sec:.1f}초"
                    elif total_sec < 3600:
                        time_text = f"{total_sec/60:.1f}분"
                    else:
                        time_text = f"{total_sec/3600:.1f}시간"
                    
                    self.performance_labels['total_processing_time'].config(
                        text=time_text,
                        foreground="blue"
                    )
                else:
                    self.performance_labels['total_processing_time'].config(text="계산 중...", foreground="gray")
            else:
                # 데이터가 없는 경우
                for key in self.performance_labels:
                    self.performance_labels[key].config(text="데이터 수집 중...", foreground="gray")
                    
        except Exception as e:
            logger.debug(f"성능 모니터링 업데이트 오류: {e}")
            for key in self.performance_labels:
                self.performance_labels[key].config(text="오류", foreground="red")
    
    def browse_file(self, source_index):
        """파일 선택"""
        # 환경변수에서 미디어 경로를 가져와서 기본 디렉토리로 설정
        media_dir = get_env_value('DEFAULT_MEDIA_PATH', "./media")
        os.makedirs(media_dir, exist_ok=True)
        
        filename = filedialog.askopenfilename(
            title=f"소스 파일 {source_index + 1} 선택",
            initialdir=media_dir,
            filetypes=[
                ("비디오 파일", "*.mp4 *.avi *.mov *.mkv *.wmv *.flv"),
                ("모든 파일", "*.*")
            ]
        )
        if filename:
            self.source_vars[source_index].set(filename)
    
    def browse_blur_module(self):
        """블러 모듈 파일 선택"""
        # 환경변수에서 블러 모듈 경로를 가져와서 해당 디렉토리를 기본으로 설정
        default_blur_path = get_env_value('BLUR_MODULE_PATH', '.')
        initial_dir = os.path.dirname(default_blur_path) if default_blur_path and os.path.isfile(default_blur_path) else "."
        filename = filedialog.askopenfilename(
            title="블러 모듈 파일 선택",
            initialdir=initial_dir,
            filetypes=[
                ("Python 파일", "*.py"),
                ("모든 파일", "*.*")
            ]
        )
        if filename:
            self.blur_module_var.set(filename)
    
    def browse_save_path(self):
        """저장 경로 선택"""
        # 환경변수에서 출력 경로를 가져와서 기본 디렉토리로 설정
        output_dir = get_env_value('DEFAULT_OUTPUT_PATH', "./output")
        os.makedirs(output_dir, exist_ok=True)
        
        directory = filedialog.askdirectory(
            title="저장 경로 선택",
            initialdir=output_dir
        )
        if directory:
            self.save_path_var.set(directory)
    
    def open_save_folder(self):
        """저장 폴더 열기"""
        save_path = self.save_path_var.get().strip()
        if not save_path:
            messagebox.showwarning("경고", "저장 경로가 설정되지 않았습니다.")
            return
        
        # 경로가 존재하지 않으면 생성
        if not os.path.exists(save_path):
            try:
                os.makedirs(save_path, exist_ok=True)
                self.log_message(f"저장 폴더 생성: {save_path}")
            except Exception as e:
                messagebox.showerror("오류", f"폴더 생성 실패: {e}")
                return
        
        try:
            # Windows
            if os.name == 'nt':
                os.startfile(save_path)
            # macOS
            elif os.name == 'posix' and os.uname().sysname == 'Darwin':
                subprocess.run(['open', save_path])
            # Linux
            else:
                subprocess.run(['xdg-open', save_path])
            
            self.log_message(f"📁 저장 폴더 열기: {save_path}")
            
        except Exception as e:
            messagebox.showerror("오류", f"폴더 열기 실패: {e}")
            self.log_message(f"폴더 열기 오류: {e}")
    
    def browse_multiple_files(self):
        """다중 파일 선택"""
        # 환경변수에서 미디어 경로를 가져와서 기본 디렉토리로 설정
        media_dir = get_env_value('DEFAULT_MEDIA_PATH', "./media")
        os.makedirs(media_dir, exist_ok=True)
        
        filenames = filedialog.askopenfilenames(
            title="다중 파일 선택",
            initialdir=media_dir,
            filetypes=[
                ("비디오 파일", "*.mp4 *.avi *.mov *.mkv *.wmv *.flv"),
                ("모든 파일", "*.*")
            ]
        )
        
        if filenames:
            # 기존 소스 모두 지우기
            for var in self.source_vars:
                var.set("")
            
            # 선택된 파일들을 소스에 설정 (최대 8개)
            for i, filename in enumerate(filenames[:8]):
                self.source_vars[i].set(filename)
            
            # 로그 메시지
            self.log_message(f"다중 파일 선택: {len(filenames[:8])}개 파일")
            for i, filename in enumerate(filenames[:8]):
                self.log_message(f"  소스 {i+1}: {os.path.basename(filename)}")
    
    def clear_all_sources(self):
        """모든 소스 지우기"""
        for var in self.source_vars:
            var.set("")
        self.log_message("모든 소스 지워짐")
    
    def start_processor(self):
        """프로세서 시작"""
        # 소스 체크
        sources = []
        for var in self.source_vars:
            source = var.get().strip()
            if source:
                sources.append(source)
        
        if not sources:
            messagebox.showerror("오류", "최소 1개의 소스를 입력하세요.")
            return
        
        try:
            max_duration_seconds = None
            if self.max_duration_var.get():
                max_duration_seconds = int(self.max_duration_var.get())
            
            blur_module_path = self.blur_module_var.get().strip() if self.blur_module_var.get().strip() else None
            
            # 초 단위 저장 간격을 프레임 수로 변환
            save_interval_seconds = self.save_interval_seconds_var.get()
            save_interval_frames = int(save_interval_seconds * self.input_fps_var.get())
            
            self.config = RTSPConfig(
                sources=sources,
                thread_count=self.thread_count_var.get(),
                max_duration_seconds=max_duration_seconds,
                frame_loss_rate=self.frame_loss_var.get() / 100.0,
                reconnect_interval=self.reconnect_var.get(),
                enable_processing=self.processing_var.get(),
                blur_module_path=blur_module_path,
                save_enabled=self.save_enabled_var.get(),
                save_path=self.save_path_var.get(),
                save_interval=save_interval_frames,
                save_format=self.container_format_var.get(),
                input_fps=self.input_fps_var.get(),
                force_fps=self.force_fps_var.get(),
                processing_queue_size=self.processing_queue_size_var.get(),
                preview_queue_size=self.preview_queue_size_var.get(),
                # 확장된 코덱 설정
                container_format=self.container_format_var.get(),
                video_codec=self.video_codec_var.get(),
                compression_level=self.compression_level_var.get(),
                quality_mode=self.quality_mode_var.get(),
                bitrate=self.bitrate_var.get(),
                max_bitrate=self.max_bitrate_var.get(),
                ffmpeg_preset=self.preset_var.get(),
                ffmpeg_tune=self.tune_var.get(),
                ffmpeg_profile=self.profile_var.get(),
                hardware_acceleration=self.hardware_accel_var.get(),
                pixel_format=self.pixel_format_var.get(),
                keyframe_interval=self.keyframe_interval_var.get(),
                extra_options=self.extra_options_var.get(),
                # 오버레이 설정
                overlay_enabled=self.overlay_enabled_var.get(),
                latitude=self.latitude_var.get(),
                longitude=self.longitude_var.get(),
                # 미리보기 설정
                preview_enabled=self.preview_enabled,
                # 블러 설정
                blur_enabled=self.blur_enabled_var.get(),
                # 고성능 모드 설정
                high_performance_mode=self.high_performance_var.get()
            )
            
            self.processor = RTSPProcessor(self.config)
            
            # 🆕 정확한 프로세서 시작 시간 기록 (processor.start() 직전)
            self.processor_start_time = time.time()
            self.processor.start()
            
            # 🆕 FPS 계산을 위한 변수들 초기화
            self.fps_history = []
            self.last_frame_count = 0
            self.last_fps_time = self.processor_start_time
            
            # 쓰레드별 미리보기 UI 생성
            self.create_thread_previews()
            
            self.start_time = time.time()  # GUI 시작 시간 (호환성 유지)
            self.running = True
            
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            
            # 소스 할당 로그
            thread_source_mapping = []
            for i in range(self.config.thread_count):
                source_index = i % len(sources)
                source_name = self.processor.extract_source_name(sources[source_index])
                thread_source_mapping.append(f"쓰레드 {i}: {source_name}")
            
            self.log_message("🚀 소스 프로세서 시작됨")
            self.log_message(f"📁 소스 {len(sources)}개 설정됨")
            self.log_message(f"🎯 입력 FPS: {self.config.input_fps}")
            self.log_message(f"📊 처리 큐 크기: {self.config.processing_queue_size}")
            self.log_message(f"📺 미리보기 큐 크기: {self.config.preview_queue_size}")
            if self.config.force_fps:
                self.log_message("⚡ FPS 강제 설정 활성화")
            if blur_module_path:
                self.log_message(f"🎨 블러 모듈: {os.path.basename(blur_module_path)}")
            
            # 블러 처리 상태 출력
            if self.config.blur_enabled:
                self.log_message("🎯 블러 처리 활성화됨")
            else:
                self.log_message("⭕ 블러 처리 비활성화됨 (성능 최적화)")
            
            # 고성능 모드 상태 출력
            if self.config.high_performance_mode:
                self.log_message("⚡ 고성능 모드 활성화됨 (오버헤드 제거, FPS는 소스에 맞춤)")
            else:
                self.log_message("🔒 정상 모드 (통계/프로파일링 활성화)")
            
            # 오버레이 상태 출력
            if self.config.overlay_enabled:
                self.log_message("📍 오버레이 활성화됨 (GPS, 시간, 프레임 정보 표시)")
            else:
                self.log_message("⭕ 오버레이 비활성화됨 (성능 개선)")
            
            # 📹 코덱 설정 정보 출력 (항상 출력)
            self.log_message("🎬 코덱 설정:")
            self.log_message(f"  컨테이너: {self.config.container_format}")
            self.log_message(f"  비디오 코덱: {self.config.video_codec}")
            self.log_message(f"  압축 레벨: {self.config.compression_level} (0=빠름/큰파일 ~ 9=느림/작은파일)")
            self.log_message(f"  품질 모드: {self.config.quality_mode}")
            self.log_message(f"  비트레이트: {self.config.bitrate} (최대: {self.config.max_bitrate})")
            self.log_message(f"  프리셋: {self.config.ffmpeg_preset}")
            self.log_message(f"  튜닝: {self.config.ffmpeg_tune}")
            self.log_message(f"  프로파일: {self.config.ffmpeg_profile}")
            self.log_message(f"  픽셀 포맷: {self.config.pixel_format}")
            self.log_message(f"  키프레임 간격: {self.config.keyframe_interval}")
            if self.config.hardware_acceleration != "none":
                self.log_message(f"🚀 하드웨어 가속: {self.config.hardware_acceleration}")
            if self.config.extra_options:
                self.log_message(f"⚙️ 추가 옵션: {self.config.extra_options}")
            
            # 📍 오버레이 설정 정보 출력
            self.log_message("📍 영상 오버레이:")
            self.log_message(f"  GPS 좌표: {self.config.latitude:.6f}, {self.config.longitude:.6f}")
            self.log_message("  표시 정보: 프레임 번호, GPS 좌표, 현재 시간, 쓰레드 ID")
            
            if self.config.save_enabled:
                self.log_message(f"💾 저장 활성화: {self.config.save_path}")
                self.log_message(f"📁 저장 간격: {save_interval_seconds}초 ({save_interval_frames}프레임)")
                if self.config.container_format in ['mp4', 'mkv', 'webm', 'avi']:
                    self.log_message(f"⏱️ 비디오 파일 길이: {save_interval_seconds}초씩 저장")
            
            self.log_message("🔄 쓰레드-소스 매핑:")
            for mapping in thread_source_mapping:
                self.log_message(f"  {mapping}")
            
        except Exception as e:
            messagebox.showerror("오류", f"프로세서 시작 실패: {e}")
            self.log_message(f"오류: {e}")
    
    def stop_processor(self):
        """프로세서 중지"""
        if self.processor:
            self.processor.stop()
            self.processor = None
        
        self.running = False
        
        # 미리보기 UI 정리
        self.clear_thread_previews()
        
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        
        # 미리보기 버튼을 기본 상태로 리셋
        self.preview_enabled = True
        self.preview_toggle_button.config(text="📺 미리보기 끄기")
        
        # 블러 버튼을 기본 상태로 리셋
        self.blur_enabled = True
        self.blur_toggle_button.config(text="🎯 블러 끄기")
        self.blur_enabled_var.set(True)
        
        # 고성능 모드 버튼을 기본 상태로 리셋
        self.high_performance_enabled = False
        self.performance_toggle_button.config(text="⚡ 고성능 켜기")
        self.high_performance_var.set(False)
        
        # 오버레이 버튼을 기본 상태로 리셋
        self.overlay_enabled = True
        self.overlay_toggle_button.config(text="📍 오버레이 끄기")
        self.overlay_enabled_var.set(True)
        
        # 🆕 FPS 계산 변수들 초기화
        self.processor_start_time = None
        self.fps_history = []
        self.last_frame_count = 0
        self.last_fps_time = 0
        
        self.log_message("소스 프로세서 중지됨")
    
    def reset_statistics(self):
        """통계 초기화"""
        if self.processor:
            self.processor.reset_statistics()
            self.start_time = time.time()
            
            # 🆕 FPS 계산 변수들도 초기화
            if hasattr(self, 'processor_start_time'):
                self.processor_start_time = time.time()
                self.fps_history = []
                self.last_frame_count = 0
                self.last_fps_time = self.processor_start_time
            
            self.log_message("통계 초기화됨")
    
    def create_thread_previews(self):
        """쓰레드별 미리보기 UI 생성"""
        self.clear_thread_previews()
        
        thread_count = self.config.thread_count
        sources = self.config.sources
        
        for thread_id in range(thread_count):
            # 해당 쓰레드에서 사용할 소스 정보
            source_index = thread_id % len(sources)
            source = sources[source_index]
            source_name = self.processor.extract_source_name(source)
            
            # 소스 타입 표시
            if self.processor.is_rtsp_source(source):
                source_type = "RTSP"
            else:
                source_type = "FILE"
            
            # 쓰레드별 프레임 생성
            thread_frame = ttk.LabelFrame(
                self.preview_scrollable_frame, 
                text=f"쓰레드 {thread_id} - {source_type}: {source_name}", 
                padding="5"
            )
            thread_frame.grid(row=thread_id // 2, column=thread_id % 2, 
                            sticky=(tk.W, tk.E), padx=5, pady=5)
            
            # 미리보기 라벨
            preview_label = ttk.Label(thread_frame, text="연결 중..." if source_type == "RTSP" else "파일 읽기 중...")
            preview_label.pack(pady=5)
            
            # 연결 상태 라벨
            if source_type == "RTSP":
                status_label = ttk.Label(thread_frame, text="● 연결 중", foreground="orange")
            else:
                status_label = ttk.Label(thread_frame, text="● 파일 읽기", foreground="blue")
            status_label.pack()
            
            # 통계 라벨
            stats_label = ttk.Label(thread_frame, text="수신: 0, 처리: 0, 저장: 0, 손실: 0")
            stats_label.pack()
            
            self.preview_labels[thread_id] = {
                'frame': thread_frame,
                'preview': preview_label,
                'status': status_label,
                'stats': stats_label,
                'source_name': source_name,
                'source_type': source_type
            }
    
    def clear_thread_previews(self):
        """쓰레드별 미리보기 UI 정리"""
        for thread_id in list(self.preview_labels.keys()):
            self.preview_labels[thread_id]['frame'].destroy()
        self.preview_labels.clear()
    
    def log_message(self, message):
        """로그 메시지 추가"""
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
    
    def update_preview(self):
        """미리보기 업데이트"""
        if not self.processor or not self.running or not self.preview_enabled:
            return
            
        # 각 쓰레드별 미리보기 업데이트
        for thread_id in self.preview_labels.keys():
            try:
                frame_data = self.processor.preview_queue[thread_id].get_nowait()
                frame, source_name = frame_data
                
                # 프레임 크기 조정
                height, width = frame.shape[:2]
                max_size = 400
                if width > max_size or height > max_size:
                    if width > height:
                        new_width = max_size
                        new_height = int(height * max_size / width)
                    else:
                        new_height = max_size
                        new_width = int(width * max_size / height)
                    frame = cv2.resize(frame, (new_width, new_height))
                
                # OpenCV BGR을 RGB로 변환
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(frame_rgb)
                imgtk = ImageTk.PhotoImage(image=img)
                
                # 미리보기 업데이트
                preview_label = self.preview_labels[thread_id]['preview']
                preview_label.configure(image=imgtk)
                preview_label.image = imgtk
                
            except (queue.Empty, KeyError):
                pass
    
    def update_statistics(self):
        """통계 업데이트"""
        if not self.processor or not self.running:
            return
            
        stats = self.processor.get_statistics()
        
        # 🆕 정확한 실행 시간 계산 (프로세서 시작 시간 기준)
        if hasattr(self, 'processor_start_time') and self.processor_start_time:
            runtime = time.time() - self.processor_start_time
        else:
            runtime = time.time() - self.start_time if self.start_time else 0
        
        # 전체 통계 라벨 업데이트
        self.stats_labels['received_frames'].config(text=str(stats['received_frames']))
        self.stats_labels['processed_frames'].config(text=str(stats['processed_frames']))
        self.stats_labels['saved_frames'].config(text=str(stats['saved_frames']))
        self.stats_labels['lost_frames'].config(text=str(stats['lost_frames']))
        self.stats_labels['error_frames'].config(text=str(stats['error_frames']))
        self.stats_labels['loss_rate'].config(text=f"{stats['loss_rate']:.2f}")
        self.stats_labels['processing_rate'].config(text=f"{stats['processing_rate']:.2f}")
        self.stats_labels['save_rate'].config(text=f"{stats['save_rate']:.2f}")
        
        # 🆕 개선된 FPS 계산 (전체 평균 + 실시간 FPS)
        if runtime > 0 and stats['processed_frames'] > 0:
            # 전체 평균 FPS
            avg_fps = stats['processed_frames'] / runtime
            
            # 실시간 FPS 계산 (최근 1초간)
            current_time = time.time()
            current_frames = stats['processed_frames']
            
            if hasattr(self, 'last_fps_time') and self.last_fps_time > 0:
                time_diff = current_time - self.last_fps_time
                frame_diff = current_frames - self.last_frame_count
                
                if time_diff >= 1.0:  # 1초마다 실시간 FPS 계산
                    realtime_fps = frame_diff / time_diff if time_diff > 0 else 0
                    
                    # FPS 이력 관리 (최근 10초)
                    self.fps_history.append(realtime_fps)
                    if len(self.fps_history) > 10:
                        self.fps_history.pop(0)
                    
                    # 다음 계산을 위해 업데이트
                    self.last_fps_time = current_time
                    self.last_frame_count = current_frames
                    
                    # 평균 FPS와 실시간 FPS 표시 (평균이 앞에)
                    fps_text = f"평균: {avg_fps:.1f} FPS (실시간: {realtime_fps:.1f})"
                    
                    # 색상은 실시간 FPS 기준으로 설정
                    if self.config and hasattr(self.config, 'input_fps'):
                        target_fps = self.config.input_fps
                        if realtime_fps >= target_fps * 0.9:
                            fps_color = "green"
                        elif realtime_fps >= target_fps * 0.5:
                            fps_color = "orange" 
                        else:
                            fps_color = "red"
                    else:
                        fps_color = "blue"
                else:
                    # 1초가 지나지 않았으면 이전 값 유지하고 평균만 업데이트
                    if len(self.fps_history) > 0:
                        last_realtime_fps = self.fps_history[-1]
                        fps_text = f"평균: {avg_fps:.1f} FPS (실시간: {last_realtime_fps:.1f})"
                        # 색상도 실시간 FPS 기준
                        if self.config and hasattr(self.config, 'input_fps'):
                            target_fps = self.config.input_fps
                            if last_realtime_fps >= target_fps * 0.9:
                                fps_color = "green"
                            elif last_realtime_fps >= target_fps * 0.5:
                                fps_color = "orange" 
                            else:
                                fps_color = "red"
                        else:
                            fps_color = "blue"
                    else:
                        fps_text = f"평균: {avg_fps:.1f} FPS (초기화 중)"
                        fps_color = "gray"
            else:
                # 초기화
                self.last_fps_time = current_time
                self.last_frame_count = current_frames
                fps_text = f"평균: {avg_fps:.1f} FPS (초기화 중)"
                fps_color = "gray"
            
            self.stats_labels['processing_fps'].config(text=fps_text, foreground=fps_color)
        else:
            self.stats_labels['processing_fps'].config(text="평균: 0.0 FPS (대기 중)", foreground="gray")
        
        self.stats_labels['thread_count'].config(text=str(stats['thread_count']))
        self.stats_labels['queue_size'].config(text=str(stats['queue_size']))
        self.stats_labels['runtime'].config(text=f"{runtime:.1f}")
        
        # 📹 코덱 정보 업데이트 (더 자세한 정보 표시)
        if self.config and hasattr(self.config, 'video_codec'):
            # 현재 코덱 정보
            codec_name = {
                'libx264': 'H.264/AVC',
                'libx265': 'H.265/HEVC', 
                'libvpx-vp9': 'VP9',
                'libaom-av1': 'AV1',
                'libxvid': 'Xvid',
                'libx262': 'H.262'
            }.get(self.config.video_codec, self.config.video_codec)
            
            # 하드웨어 가속 정보
            hw_accel = ""
            if hasattr(self.config, 'hardware_acceleration') and self.config.hardware_acceleration != 'none':
                hw_accel = f" + {self.config.hardware_acceleration.upper()}"
            
            # 현재 코덱 + 추가 정보
            codec_info = f"{codec_name} | 레벨 {self.config.compression_level} | {self.config.quality_mode.upper()}{hw_accel}"
            self.stats_labels['current_codec_info'].config(text=codec_info, foreground='blue')
            
            # 인코딩 성능 정보 (더 자세히)
            if runtime > 0 and stats['processed_frames'] > 0:
                encoding_fps = stats['processed_frames'] / runtime
                target_fps = self.config.input_fps
                efficiency = (encoding_fps / target_fps) * 100 if target_fps > 0 else 0
                
                if encoding_fps >= target_fps * 0.9:
                    perf_text = f"{encoding_fps:.1f}/{target_fps:.1f} FPS ({efficiency:.0f}% 실시간)"
                    perf_color = "green"
                elif encoding_fps >= target_fps * 0.5:
                    perf_text = f"{encoding_fps:.1f}/{target_fps:.1f} FPS ({efficiency:.0f}% 준실시간)"
                    perf_color = "orange"
                else:
                    perf_text = f"{encoding_fps:.1f}/{target_fps:.1f} FPS ({efficiency:.0f}% 느림)"
                    perf_color = "red"
                
                self.stats_labels['encoding_performance'].config(text=perf_text, foreground=perf_color)
            else:
                self.stats_labels['encoding_performance'].config(text="계산 중...", foreground="gray")
            
            # 파일 포맷 정보 (더 자세히)
            format_info = f"{self.config.container_format.upper()} | {self.config.quality_mode.upper()} | {self.config.bitrate}"
            if hasattr(self.config, 'ffmpeg_preset'):
                format_info += f" | {self.config.ffmpeg_preset}"
            self.stats_labels['file_format'].config(text=format_info, foreground='purple')
        else:
            # 설정이 없을 때
            self.stats_labels['current_codec_info'].config(text="설정 없음", foreground="gray")
            self.stats_labels['encoding_performance'].config(text="대기 중", foreground="gray")
            self.stats_labels['file_format'].config(text="대기 중", foreground="gray")
        
        # 쓰레드별 통계 및 연결 상태 업데이트
        self.update_thread_stats()
        
        # 코덱 성능 정보 업데이트
        self.update_codec_performance()
        
        # 🆕 리소스 및 성능 모니터링 업데이트
        self.update_resource_monitoring()
        self.update_performance_monitoring()
        
        # 최대 처리 시간 도달 시 자동 중지
        if (self.config and self.config.max_duration_seconds):
            # 모든 스레드의 시작 시간을 확인하기 위해 가장 오래된 스레드 기준
            oldest_start_time = min([stat.get('start_time', time.time()) for stat in self.connection_status.values()], default=time.time())
            elapsed_time = time.time() - oldest_start_time
            if elapsed_time >= self.config.max_duration_seconds:
                self.stop_processor()
                self.log_message(f"최대 처리 시간({self.config.max_duration_seconds}초)에 도달하여 자동 중지됨")
    
    def update_codec_performance(self):
        """코덱 성능 정보 실시간 업데이트"""
        if not self.processor or not self.running:
            # 대기 상태 표시
            self.codec_perf_labels['encoding_speed'].config(text="대기 중...", foreground="gray")
            self.codec_perf_labels['compression_ratio'].config(text="대기 중...", foreground="gray")
            self.codec_perf_labels['avg_bitrate'].config(text="대기 중...", foreground="gray")
            self.codec_perf_labels['current_fps'].config(text="대기 중...", foreground="gray")
            self.codec_perf_labels['estimated_size'].config(text="대기 중...", foreground="gray")
            return
        
        try:
            stats = self.processor.get_statistics()
            runtime = time.time() - self.start_time if self.start_time else 0
            
            # 인코딩 속도 계산
            if runtime > 0 and stats['processed_frames'] > 0:
                encoding_fps = stats['processed_frames'] / runtime
                if encoding_fps >= self.config.input_fps * 0.9:
                    speed_text = f"{encoding_fps:.1f} FPS (실시간)"
                    speed_color = "green"
                elif encoding_fps >= self.config.input_fps * 0.5:
                    speed_text = f"{encoding_fps:.1f} FPS (준실시간)"
                    speed_color = "orange"
                else:
                    speed_text = f"{encoding_fps:.1f} FPS (느림)"
                    speed_color = "red"
                
                self.codec_perf_labels['encoding_speed'].config(text=speed_text, foreground=speed_color)
            
            # 압축 비율 계산 (예상)
            if hasattr(self.config, 'video_codec'):
                codec = self.config.video_codec
                compression = self.config.compression_level
                
                # 코덱별 압축 비율 추정
                compression_ratios = {
                    'libx264': {0: '30%', 3: '50%', 6: '70%', 9: '85%'},
                    'libx265': {0: '50%', 3: '65%', 6: '80%', 9: '90%'},
                    'libvpx-vp9': {0: '45%', 3: '60%', 6: '75%', 9: '88%'},
                    'libaom-av1': {0: '60%', 3: '70%', 6: '85%', 9: '92%'}
                }
                
                if codec in compression_ratios:
                    # 가장 가까운 압축 레벨 찾기
                    closest_level = min(compression_ratios[codec].keys(), key=lambda x: abs(x - compression))
                    ratio_text = compression_ratios[codec][closest_level]
                    self.codec_perf_labels['compression_ratio'].config(text=ratio_text, foreground="blue")
            
            # 평균 비트레이트 (설정값 표시)
            if hasattr(self.config, 'bitrate'):
                bitrate_text = f"{self.config.bitrate} ({self.config.quality_mode.upper()})"
                self.codec_perf_labels['avg_bitrate'].config(text=bitrate_text, foreground="purple")
            
            # 현재 FPS
            current_fps_text = f"{self.config.input_fps:.1f} FPS"
            if hasattr(self.config, 'force_fps') and self.config.force_fps:
                current_fps_text += " (강제)"
            self.codec_perf_labels['current_fps'].config(text=current_fps_text, foreground="darkgreen")
            
            # 예상 파일 크기 (1분 기준)
            if hasattr(self.config, 'video_codec') and stats['processed_frames'] > 0:
                codec = self.config.video_codec
                compression = self.config.compression_level
                
                # 코덱별 예상 파일 크기 (1분 1080p 기준)
                size_estimates = {
                    'libx264': {0: '100MB', 3: '70MB', 6: '45MB', 9: '30MB'},
                    'libx265': {0: '50MB', 3: '35MB', 6: '25MB', 9: '15MB'},
                    'libvpx-vp9': {0: '60MB', 3: '40MB', 6: '28MB', 9: '18MB'},
                    'libaom-av1': {0: '45MB', 3: '30MB', 6: '20MB', 9: '12MB'}
                }
                
                if codec in size_estimates:
                    closest_level = min(size_estimates[codec].keys(), key=lambda x: abs(x - compression))
                    size_text = f"{size_estimates[codec][closest_level]} (1분 기준)"
                    self.codec_perf_labels['estimated_size'].config(text=size_text, foreground="brown")
            
        except Exception as e:
            # 오류 발생 시 오류 표시
            for key in self.codec_perf_labels:
                self.codec_perf_labels[key].config(text="오류", foreground="red")
    
    def update_thread_stats(self):
        """쓰레드별 통계 및 연결 상태 업데이트"""
        if not self.processor or not self.running:
            return
            
        connection_status = self.processor.get_statistics()['connection_status']
        
        for thread_id in self.preview_labels.keys():
            try:
                # 쓰레드별 통계 가져오기
                thread_stats = self.processor.get_thread_statistics(thread_id)
                
                # 연결 상태 업데이트
                status_label = self.preview_labels[thread_id]['status']
                source_type = self.preview_labels[thread_id]['source_type']
                
                if source_type == "RTSP":
                    # RTSP 연결 상태
                    if connection_status[thread_id]['connected']:
                        last_frame_time = connection_status[thread_id]['last_frame_time']
                        if time.time() - last_frame_time < 5:  # 5초 이내 프레임 수신
                            status_label.config(text="● 연결됨", foreground="green")
                        else:
                            status_label.config(text="● 지연됨", foreground="orange")
                    else:
                        status_label.config(text="● 연결 안됨", foreground="red")
                else:
                    # 파일 읽기 상태
                    if connection_status[thread_id]['connected']:
                        last_frame_time = connection_status[thread_id]['last_frame_time']
                        if time.time() - last_frame_time < 5:
                            status_label.config(text="● 파일 읽기 중", foreground="green")
                        else:
                            status_label.config(text="● 파일 끝", foreground="blue")
                    else:
                        status_label.config(text="● 파일 오류", foreground="red")
                
                # 통계 업데이트
                if thread_stats:
                    received = thread_stats['received_frames']
                    processed = thread_stats['processed_frames']
                    saved = thread_stats['saved_frames']
                    lost = thread_stats['lost_frames']
                    error = thread_stats['error_frames']
                    
                    stats_text = f"수신: {received}, 처리: {processed}"
                    if self.config.save_enabled:
                        stats_text += f", 저장: {saved}"
                    stats_text += f", 손실: {lost}"
                    
                    if error > 0:
                        stats_text += f", 오류: {error}"
                    
                    if received > 0:
                        processing_rate = (processed / received) * 100
                        stats_text += f"\n처리율: {processing_rate:.1f}%"
                        
                        if self.config.save_enabled and processed > 0:
                            save_rate = (saved / processed) * 100
                            stats_text += f", 저장율: {save_rate:.1f}%"
                    
                    self.preview_labels[thread_id]['stats'].config(text=stats_text)
                
            except (KeyError, Exception) as e:
                logger.debug(f"쓰레드 {thread_id} 통계 업데이트 오류: {e}")
    
    def start_update_thread(self):
        """업데이트 쓰레드 시작"""
        def update_loop():
            while True:
                try:
                    self.root.after(0, self.update_preview)
                    self.root.after(0, self.update_statistics)
                    time.sleep(0.1)  # 100ms마다 업데이트
                except:
                    break
        
        self.update_thread = threading.Thread(target=update_loop, daemon=True)
        self.update_thread.start()
    
    def toggle_preview(self):
        """실시간 미리보기 토글"""
        self.preview_enabled = not self.preview_enabled
        
        # 프로세서가 실행 중인 경우 config 업데이트
        if self.processor and self.config:
            self.config.preview_enabled = self.preview_enabled
            self.processor.config.preview_enabled = self.preview_enabled
        
        if self.preview_enabled:
            self.preview_toggle_button.config(text="📺 미리보기 끄기")
            self.log_message("🔴 실시간 미리보기 활성화됨 (성능 영향: 중간)")
        else:
            self.preview_toggle_button.config(text="📺 미리보기 켜기")
            self.log_message("⚫ 실시간 미리보기 비활성화됨 (성능 개선: 큐 처리 생략)")
            
            # 미리보기 비활성화 시 기존 미리보기 이미지들을 클리어
            for thread_id in self.preview_labels.keys():
                preview_label = self.preview_labels[thread_id]['preview']
                preview_label.configure(image='', text="미리보기 비활성화됨")
                preview_label.image = None
                
            # 미리보기 큐 비우기 (메모리 절약)
            if self.processor:
                for thread_id in range(10):
                    try:
                        while not self.processor.preview_queue[thread_id].empty():
                            self.processor.preview_queue[thread_id].get_nowait()
                    except (queue.Empty, KeyError):
                        pass

    def toggle_blur(self):
        """블러 처리 토글"""
        self.blur_enabled = not self.blur_enabled
        
        # 프로세서가 실행 중인 경우 config 업데이트
        if self.processor and self.config:
            self.config.blur_enabled = self.blur_enabled
            self.processor.config.blur_enabled = self.blur_enabled
        
        # 체크박스 상태도 업데이트
        self.blur_enabled_var.set(self.blur_enabled)
        
        if self.blur_enabled:
            self.blur_toggle_button.config(text="🎯 블러 끄기")
            self.log_message("🎯 블러 처리 활성화됨 (성능 영향: 높음)")
        else:
            self.blur_toggle_button.config(text="🎯 블러 켜기")
            self.log_message("⭕ 블러 처리 비활성화됨 (성능 개선: 상당함)")

    def on_blur_checkbox_change(self):
        """블러 체크박스 변경 이벤트"""
        self.blur_enabled = self.blur_enabled_var.get()
        
        # 프로세서가 실행 중인 경우 config 업데이트
        if self.processor and self.config:
            self.config.blur_enabled = self.blur_enabled
            self.processor.config.blur_enabled = self.blur_enabled
        
        # 버튼 텍스트 업데이트
        if self.blur_enabled:
            self.blur_toggle_button.config(text="🎯 블러 끄기")
            if self.running:
                self.log_message("🎯 블러 처리 활성화됨 (체크박스)")
        else:
            self.blur_toggle_button.config(text="🎯 블러 켜기")
            if self.running:
                self.log_message("⭕ 블러 처리 비활성화됨 (체크박스)")

    def on_closing(self):
        """창 닫기 처리"""
        if self.processor:
            self.processor.stop()
        self.root.destroy()

    def toggle_performance(self):
        """고성능 모드 토글"""
        self.high_performance_enabled = not self.high_performance_enabled
        
        # 프로세서가 실행 중인 경우 config 업데이트
        if self.processor and self.config:
            self.config.high_performance_mode = self.high_performance_enabled
            self.processor.config.high_performance_mode = self.high_performance_enabled
        
        # 체크박스 상태도 업데이트
        self.high_performance_var.set(self.high_performance_enabled)
        
        if self.high_performance_enabled:
            self.performance_toggle_button.config(text="⚡ 고성능 끄기")
            self.log_message("⚡ 고성능 모드 활성화됨 (오버헤드 제거, FPS는 소스에 맞춤)")
        else:
            self.performance_toggle_button.config(text="⚡ 고성능 켜기")
            self.log_message("🔒 고성능 모드 비활성화됨 (정상 모드)")

    def on_performance_checkbox_change(self):
        """고성능 모드 체크박스 변경 이벤트"""
        self.high_performance_enabled = self.high_performance_var.get()
        
        # 프로세서가 실행 중인 경우 config 업데이트
        if self.processor and self.config:
            self.config.high_performance_mode = self.high_performance_enabled
            self.processor.config.high_performance_mode = self.high_performance_enabled
        
        # 버튼 텍스트 업데이트
        if self.high_performance_enabled:
            self.performance_toggle_button.config(text="⚡ 고성능 끄기")
            if self.running:
                self.log_message("⚡ 고성능 모드 활성화됨 (체크박스)")
        else:
            self.performance_toggle_button.config(text="⚡ 고성능 켜기")
            if self.running:
                self.log_message("🔒 고성능 모드 비활성화됨 (체크박스)")

    def toggle_overlay(self):
        """오버레이 토글"""
        self.overlay_enabled = not self.overlay_enabled
        
        # 프로세서가 실행 중인 경우 config 업데이트
        if self.processor and self.config:
            self.config.overlay_enabled = self.overlay_enabled
            self.processor.config.overlay_enabled = self.overlay_enabled
        
        # 체크박스 상태도 업데이트
        self.overlay_enabled_var.set(self.overlay_enabled)
        
        if self.overlay_enabled:
            self.overlay_toggle_button.config(text="📍 오버레이 끄기")
            self.log_message("📍 오버레이 활성화됨 (성능 영향: 높음)")
        else:
            self.overlay_toggle_button.config(text="📍 오버레이 켜기")
            self.log_message("⭕ 오버레이 비활성화됨 (성능 개선: 상당함)")

    def on_overlay_checkbox_change(self):
        """오버레이 체크박스 변경 이벤트"""
        self.overlay_enabled = self.overlay_enabled_var.get()
        
        # 프로세서가 실행 중인 경우 config 업데이트
        if self.processor and self.config:
            self.config.overlay_enabled = self.overlay_enabled
            self.processor.config.overlay_enabled = self.overlay_enabled
        
        # 버튼 텍스트 업데이트
        if self.overlay_enabled:
            self.overlay_toggle_button.config(text="📍 오버레이 끄기")
            if self.running:
                self.log_message("📍 오버레이 활성화됨 (체크박스)")
        else:
            self.overlay_toggle_button.config(text="📍 오버레이 켜기")
            if self.running:
                self.log_message("⭕ 오버레이 비활성화됨 (체크박스)")

def main():
    """메인 함수"""
    root = tk.Tk()
    app = RTSPProcessorGUI(root)
    
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()