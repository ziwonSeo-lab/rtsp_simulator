"""RTSP 클라이언트 통계 및 모니터링 모듈"""

import threading
import time
import logging
import psutil
from collections import deque
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# GPU 모듈 import 시도
try:
    import GPUtil
    GPU_AVAILABLE = True
except ImportError:
    GPU_AVAILABLE = False
    GPUtil = None


class FrameStatistics:
    """프레임 통계 관리 클래스"""
    
    def __init__(self):
        self.lock = threading.Lock()
        self.received_frames = 0
        self.processed_frames = 0
        self.saved_frames = 0
        self.lost_frames = 0
        self.error_frames = 0
        self.total_frames = 0
    
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


class FrameCounter:
    """간단한 프레임 카운터 클래스"""
    
    def __init__(self):
        self.lock = threading.Lock()
        self.count = 0
        self.start_time = time.time()
    
    def increment(self):
        with self.lock:
            self.count += 1
    
    def get_count(self):
        with self.lock:
            return self.count
    
    def get_fps(self):
        with self.lock:
            elapsed = time.time() - self.start_time
            return self.count / max(elapsed, 0.001)
    
    def reset(self):
        with self.lock:
            self.count = 0
            self.start_time = time.time()


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
        if not self.monitoring:
            self.monitoring = True
            self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self.monitor_thread.start()
            logger.info("리소스 모니터링 시작됨")
    
    def stop_monitoring(self):
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
        logger.info("리소스 모니터링 중지됨")
    
    def _monitor_loop(self):
        while self.monitoring:
            try:
                cpu_percent = self.process.cpu_percent()
                cpu_system = psutil.cpu_percent()
                
                memory_info = self.process.memory_info()
                memory_percent = self.process.memory_percent()
                system_memory = psutil.virtual_memory()
                
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
                
                # 메모리 정리 (30초마다)
                if len(self.cpu_history) % 30 == 0:
                    import gc
                    gc.collect()
                
                if len(self.cpu_history) > 0:
                    # CPU 사용률이 높으면 더 오래 대기
                    last_cpu = self.cpu_history[-1]['process_cpu']
                    if last_cpu > 80:
                        time.sleep(2.0)  # CPU 높을 때 2초 대기
                    elif last_cpu > 50:
                        time.sleep(1.5)  # CPU 중간일 때 1.5초 대기
                    else:
                        time.sleep(1.0)  # CPU 낮을 때 1초 대기
                else:
                    time.sleep(1.0)
                
            except Exception as e:
                logger.error(f"리소스 모니터링 오류: {e}")
                time.sleep(5.0)  # 오류 시 5초 대기
    
    def _get_gpu_info(self) -> Optional[Dict[str, Any]]:
        if not self.gpu_available:
            return None
        
        try:
            gpus = GPUtil.getGPUs()
            if not gpus:
                logger.debug("GPU가 감지되지 않음")
                return None
            
            gpu_data = {
                'timestamp': time.time(),
                'gpus': []
            }
            
            for i, gpu in enumerate(gpus):
                try:
                    # GPU 정보 안전하게 수집
                    gpu_info = {
                        'id': i,
                        'name': getattr(gpu, 'name', 'Unknown GPU'),
                        'load': getattr(gpu, 'load', 0) * 100,
                        'memory_used_mb': getattr(gpu, 'memoryUsed', 0),
                        'memory_total_mb': getattr(gpu, 'memoryTotal', 1),
                        'temperature': getattr(gpu, 'temperature', 0)
                    }
                    # 메모리 퍼센트 계산 (0으로 나누기 방지)
                    if gpu_info['memory_total_mb'] > 0:
                        gpu_info['memory_percent'] = (gpu_info['memory_used_mb'] / gpu_info['memory_total_mb']) * 100
                    else:
                        gpu_info['memory_percent'] = 0
                    
                    gpu_data['gpus'].append(gpu_info)
                except Exception as gpu_error:
                    logger.warning(f"GPU {i} 정보 수집 실패: {gpu_error}")
                    continue
            
            return gpu_data if gpu_data['gpus'] else None
            
        except Exception as e:
            logger.warning(f"GPU 정보 가져오기 실패: {e}")
            # 연속적인 실패 시 GPU 사용 불가능으로 설정
            self.gpu_available = False
            return None
    
    def get_current_stats(self) -> Dict[str, Any]:
        with self.lock:
            stats = {
                'cpu': self.cpu_history[-1] if self.cpu_history else None,
                'ram': self.ram_history[-1] if self.ram_history else None,
                'gpu': self.gpu_history[-1] if self.gpu_history else None,
                'gpu_available': self.gpu_available
            }
        return stats
    
    def get_summary_stats(self) -> Dict[str, Any]:
        with self.lock:
            if not self.cpu_history:
                return {}
            
            cpu_process = [entry['process_cpu'] for entry in self.cpu_history]
            cpu_system = [entry['system_cpu'] for entry in self.cpu_history]
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
    
    def start_profile(self, name: str):
        """프로파일 시작"""
        with self.lock:
            self.profiles[name] = {
                'start_time': time.time(),
                'end_time': None,
                'duration': None
            }
    
    def end_profile(self, name: str):
        """프로파일 종료"""
        with self.lock:
            if name in self.profiles:
                self.profiles[name]['end_time'] = time.time()
                self.profiles[name]['duration'] = self.profiles[name]['end_time'] - self.profiles[name]['start_time']
    
    def get_profile(self, name: str) -> Optional[Dict[str, Any]]:
        """프로파일 결과 조회"""
        with self.lock:
            return self.profiles.get(name)
    
    def get_all_profiles(self) -> Dict[str, Dict[str, Any]]:
        """모든 프로파일 결과 조회"""
        with self.lock:
            return self.profiles.copy()
    
    def clear_profiles(self):
        """프로파일 데이터 초기화"""
        with self.lock:
            self.profiles.clear()
            self.thread_profiles.clear()