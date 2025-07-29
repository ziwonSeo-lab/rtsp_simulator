"""
RTSP 멀티프로세싱 프로세서 모듈

SharedPoolRTSPProcessor 클래스를 포함하여 멀티프로세싱 환경에서
RTSP 스트림을 캡처, 처리, 저장하는 시스템을 관리합니다.

이 모듈은 multi-process_rtsp.py에서 추출되었으며,
독립된 모듈로 사용할 수 있도록 설계되었습니다.
"""

import os
import time
import logging
from multiprocessing import Manager, Queue, Process, Event
from typing import Dict, Any, Optional
import queue

# 로컬 모듈 임포트
from .config import RTSPConfig
from .statistics import FrameCounter, ResourceMonitor, PerformanceProfiler
from .workers import rtsp_capture_process, blur_worker_process, save_worker_process, file_move_worker_process

logger = logging.getLogger(__name__)


class SharedPoolRTSPProcessor:
    """
    공유 풀 기반 RTSP 처리 시스템
    
    멀티프로세싱을 사용하여 RTSP 스트림을 병렬로 처리하는 프로세서입니다.
    캡처, 블러 처리, 저장을 각각 별도의 프로세스에서 수행하여
    높은 성능과 안정성을 제공합니다.
    
    Features:
    - 멀티프로세스 기반 병렬 처리
    - 스레드별 RTSP 소스 할당
    - 실시간 통계 및 모니터링
    - 리소스 모니터링
    - 성능 프로파일링
    """
    
    def __init__(self, config: RTSPConfig):
        """
        SharedPoolRTSPProcessor 초기화
        
        Args:
            config (RTSPConfig): RTSP 처리 설정
        """
        self.config = config
        self.frame_counter = FrameCounter()
        self.resource_monitor = ResourceMonitor()
        self.performance_profiler = PerformanceProfiler()
        
        # 멀티프로세싱 요소들
        self.manager = Manager()
        self.blur_queue = Queue(maxsize=config.blur_queue_size)
        self.save_queue = Queue(maxsize=config.save_queue_size)
        self.preview_queue = Queue(maxsize=config.preview_queue_size)
        self.stats_dict = self.manager.dict()
        self.stop_event = Event()
        
        # 2단계 저장을 위한 파일 이동 큐
        if hasattr(config, 'two_stage_storage') and config.two_stage_storage:
            self.file_move_queue = Queue(maxsize=getattr(config, 'file_move_queue_size', 100))
        else:
            self.file_move_queue = None
        
        # 프로세스 리스트
        self.capture_processes = []
        self.blur_processes = []
        self.save_processes = []
        self.file_move_processes = []
        
        self.running = False
        
        # 출력 디렉토리 생성
        if config.save_enabled:
            os.makedirs(config.save_path, exist_ok=True)
    
    def get_source_for_thread(self, thread_id: int) -> str:
        """
        스레드 ID에 따른 소스 반환
        
        Args:
            thread_id (int): 스레드 ID
            
        Returns:
            str: 할당된 소스 URL 또는 경로
            
        Raises:
            ValueError: 소스가 설정되지 않은 경우
        """
        if not self.config.sources:
            raise ValueError("소스가 설정되지 않았습니다.")
        
        # 순환 방식으로 소스 할당
        source_index = thread_id % len(self.config.sources)
        return self.config.sources[source_index]
    
    def is_rtsp_source(self, source: str) -> bool:
        """
        RTSP 소스인지 확인
        
        Args:
            source (str): 소스 URL 또는 경로
            
        Returns:
            bool: RTSP 소스 여부
        """
        return source.lower().startswith(('rtsp://', 'http://', 'https://'))
    
    def extract_source_name(self, source: str) -> str:
        """
        소스에서 이름 추출
        
        Args:
            source (str): 소스 URL 또는 경로
            
        Returns:
            str: 추출된 소스 이름
        """
        try:
            if self.is_rtsp_source(source):
                if '://' in source:
                    parts = source.split('://', 1)[1]
                    if '/' in parts:
                        return parts.split('/', 1)[1]
                    else:
                        return parts
            else:
                return os.path.basename(source)
            return source
        except:
            return source
    
    def start(self):
        """
        RTSP 처리 시스템 시작
        
        모든 워커 프로세스를 시작하고 모니터링을 활성화합니다.
        """
        logger.info("공유 풀 RTSP 처리 시스템 시작")
        self.running = True
        
        self.resource_monitor.start_monitoring()
        self.performance_profiler.start_profile("total_processing")
        
        # 스레드별 캡처 프로세스 시작
        logger.info("=" * 60)
        logger.info("🚀 프로세스 시작 - PID 정보 출력")
        logger.info("=" * 60)
        
        for thread_id in range(self.config.thread_count):
            source = self.get_source_for_thread(thread_id)
            stream_id = f"stream_{thread_id+1}"
            
            proc = Process(
                target=rtsp_capture_process,
                args=(source, stream_id, thread_id, self.blur_queue, self.preview_queue, 
                      self.stats_dict, self.stop_event, self.config),
                name=f"Capture_{stream_id}"
            )
            proc.start()
            self.capture_processes.append(proc)
            
            logger.info(f"📹 캡처 프로세스 시작: {stream_id} (PID: {proc.pid}) - {source}")
        
        # 블러 처리 워커들 시작
        logger.info("-" * 40)
        for i in range(self.config.blur_workers):
            proc = Process(
                target=blur_worker_process,
                args=(i+1, self.blur_queue, self.save_queue, self.preview_queue,
                      self.stats_dict, self.stop_event),
                name=f"BlurWorker_{i+1}"
            )
            proc.start()
            self.blur_processes.append(proc)
            logger.info(f"🔍 블러 워커 시작: Worker {i+1} (PID: {proc.pid})")
        
        # 저장 워커들 시작
        if self.config.save_enabled:
            logger.info("-" * 40)
            for i in range(self.config.save_workers):
                proc = Process(
                    target=save_worker_process,
                    args=(i+1, self.save_queue, self.stats_dict, 
                          self.stop_event, self.config.save_path, 
                          self.file_move_queue, self.config),
                    name=f"SaveWorker_{i+1}"
                )
                proc.start()
                self.save_processes.append(proc)
                logger.info(f"💾 저장 워커 시작: Worker {i+1} (PID: {proc.pid})")
        
        # 파일 이동 워커들 시작 (2단계 저장 활성화 시)
        if (hasattr(self.config, 'two_stage_storage') and self.config.two_stage_storage and 
            self.file_move_queue is not None):
            logger.info("-" * 40)
            for i in range(getattr(self.config, 'file_move_workers', 2)):
                proc = Process(
                    target=file_move_worker_process,
                    args=(i+1, self.file_move_queue, self.stats_dict, 
                          self.stop_event, self.config.ssd_temp_path, 
                          self.config.hdd_final_path, self.config.temp_file_prefix),
                    name=f"FileMoveWorker_{i+1}"
                )
                proc.start()
                self.file_move_processes.append(proc)
                logger.info(f"🚛 파일 이동 워커 시작: Worker {i+1} (PID: {proc.pid})")
        
        total = (len(self.capture_processes) + len(self.blur_processes) + 
                len(self.save_processes) + len(self.file_move_processes))
        logger.info("=" * 60)
        logger.info(f"✅ 총 {total}개 프로세스 시작 완료")
        logger.info(f"   📹 캡처: {len(self.capture_processes)}개")
        logger.info(f"   🔍 블러: {len(self.blur_processes)}개")
        logger.info(f"   💾 저장: {len(self.save_processes)}개")
        logger.info(f"   🚛 이동: {len(self.file_move_processes)}개")
        logger.info("=" * 60)
    
    def stop(self):
        """
        RTSP 처리 시스템 종료
        
        모든 워커 프로세스를 안전하게 종료하고 리소스를 정리합니다.
        """
        logger.info("공유 풀 시스템 종료 시작...")
        self.running = False
        
        self.performance_profiler.end_profile("total_processing")
        
        # 종료 이벤트 설정
        self.stop_event.set()
        
        # 프로세스들 순서대로 종료
        all_processes = [
            ("캡처", self.capture_processes, 5),
            ("블러", self.blur_processes, 10),
            ("저장", self.save_processes, 20),
            ("파일이동", self.file_move_processes, 15)
        ]
        
        for name, processes, timeout in all_processes:
            for proc in processes:
                if proc.is_alive():
                    logger.info(f"🔄 {name} 프로세스 종료 대기: {proc.name} (PID: {proc.pid})")
                    proc.join(timeout=timeout)
                    
                    if proc.is_alive():
                        logger.warning(f"⚠️ {name} 프로세스 강제 종료: {proc.name} (PID: {proc.pid})")
                        proc.terminate()
                        proc.join(timeout=2)
                        
                        if proc.is_alive():
                            logger.error(f"❌ {name} 프로세스 강제 킬: {proc.name} (PID: {proc.pid})")
                            proc.kill()
                    else:
                        logger.info(f"✅ {name} 프로세스 정상 종료: {proc.name} (PID: {proc.pid})")
        
        self.resource_monitor.stop_monitoring()
        logger.info("✅ 시스템 종료 완료")
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        통계 정보 반환
        
        Returns:
            Dict[str, Any]: 종합 통계 정보
        """
        # 프로세스별 통계를 집계
        total_received = sum(v for k, v in self.stats_dict.items() if k.endswith('_received'))
        total_processed = sum(v for k, v in self.stats_dict.items() if k.endswith('_processed'))
        total_saved = sum(v for k, v in self.stats_dict.items() if k.endswith('_saved'))
        total_moved = sum(v for k, v in self.stats_dict.items() if k.endswith('_moved'))
        total_lost = sum(v for k, v in self.stats_dict.items() if k.endswith('_lost'))
        
        # 스레드별 연결 상태 생성
        connection_status = {}
        for i in range(self.config.thread_count):
            stream_id = f"stream_{i+1}"
            received = self.stats_dict.get(f'{stream_id}_received', 0)
            connection_status[i] = {
                'connected': received > 0,
                'last_frame_time': time.time() if received > 0 else 0,
                'start_time': time.time()
            }
        
        stats = {
            'received_frames': total_received,
            'processed_frames': total_processed,
            'saved_frames': total_saved,
            'moved_frames': total_moved,
            'lost_frames': total_lost,
            'error_frames': 0,
            'total_frames': total_received,
            'loss_rate': total_lost / max(total_received, 1) * 100,
            'processing_rate': total_processed / max(total_received, 1) * 100,
            'save_rate': total_saved / max(total_processed, 1) * 100,
            'move_rate': total_moved / max(total_saved, 1) * 100 if hasattr(self.config, 'two_stage_storage') and self.config.two_stage_storage else 0,
            'thread_count': self.config.thread_count,
            'queue_size': 0,
            'preview_queue_sizes': {0: self.preview_queue.qsize()},
            'blur_queue_size': self.blur_queue.qsize(),
            'save_queue_size': self.save_queue.qsize(),
            'file_move_queue_size': self.file_move_queue.qsize() if self.file_move_queue else 0,
            'connection_status': connection_status,
            'resource_stats': self.resource_monitor.get_current_stats(),
            'performance_stats': self.performance_profiler.get_all_profiles(),
            'two_stage_storage': hasattr(self.config, 'two_stage_storage') and self.config.two_stage_storage
        }
        
        return stats
    
    def get_preview_frame(self) -> Optional[Any]:
        """
        미리보기용 프레임 가져오기
        
        Returns:
            Optional[Any]: 미리보기 프레임 (없으면 None)
        """
        try:
            if hasattr(self.config, 'preview_enabled') and not self.config.preview_enabled:
                return None
                
            # 미리보기 큐에서 최신 프레임 가져오기 (논블로킹)
            frame_data = self.preview_queue.get_nowait()
            
            # 큐에 쌓인 오래된 프레임들 제거 (최신 프레임만 유지)
            while not self.preview_queue.empty():
                try:
                    newer_frame_data = self.preview_queue.get_nowait()
                    frame_data = newer_frame_data  # 더 새로운 프레임으로 교체
                except queue.Empty:
                    break
            
            # 프레임은 (stream_id, frame, info) 튜플 형태로 전송됨
            if isinstance(frame_data, tuple) and len(frame_data) >= 2:
                return frame_data[1]  # 실제 프레임 데이터 반환
            else:
                return frame_data  # 단일 프레임인 경우
            
        except queue.Empty:
            # 큐가 비어있음 - 정상적인 상황
            return None
        except Exception as e:
            logger.debug(f"미리보기 프레임 가져오기 실패: {e}")
            return None
    
    def get_preview_queue_size(self) -> int:
        """
        미리보기 큐 크기 반환
        
        Returns:
            int: 현재 미리보기 큐에 있는 프레임 수
        """
        try:
            return self.preview_queue.qsize()
        except:
            return 0
    
    def get_thread_statistics(self, thread_id: int) -> Dict[str, Any]:
        """
        스레드별 통계 반환
        
        Args:
            thread_id (int): 스레드 ID
            
        Returns:
            Dict[str, Any]: 스레드별 통계 정보
        """
        stream_id = f"stream_{thread_id+1}"
        received = self.stats_dict.get(f'{stream_id}_received', 0)
        processed = self.stats_dict.get(f'{stream_id}_processed', 0)
        saved = self.stats_dict.get(f'{stream_id}_saved', 0)
        moved = self.stats_dict.get(f'{stream_id}_moved', 0)
        lost = self.stats_dict.get(f'{stream_id}_lost', 0)
        
        return {
            'received_frames': received,
            'processed_frames': processed,
            'saved_frames': saved,
            'moved_frames': moved,
            'lost_frames': lost,
            'error_frames': 0,
            'total_frames': received,
            'loss_rate': lost / max(received, 1) * 100,
            'processing_rate': processed / max(received, 1) * 100,
            'save_rate': saved / max(processed, 1) * 100,
            'move_rate': moved / max(saved, 1) * 100 if hasattr(self.config, 'two_stage_storage') and self.config.two_stage_storage else 0
        }
    
    def reset_statistics(self):
        """통계 초기화"""
        self.frame_counter.reset()
        self.stats_dict.clear()
        logger.info("통계 초기화됨")