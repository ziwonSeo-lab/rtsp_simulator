"""
RTSP 영상 저장 프로세스
- 여러 RTSP 스트림을 동시에 세그먼트 단위로 저장
- 저장 완료된 파일을 블러 처리 대기 큐에 추가
- 독립적으로 실행 가능한 프로세스
"""

import os
import sys
import time
import json
import signal
import logging
import argparse
import cv2
import multiprocessing
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
import threading
import queue
import psutil

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [RECORDER] - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class RTSPRecorderConfig:
    """RTSP 녹화 설정"""
    sources: List[str]  # RTSP URL 또는 파일 경로
    output_dir: str = "./raw_videos"  # 원본 영상 저장 경로
    queue_dir: str = "./processing_queue"  # 블러 처리 대기 큐 경로
    
    # 영상 설정
    segment_duration: int = 30  # 세그먼트 길이 (초)
    input_fps: float = 15.0
    video_codec: str = "libx264"
    container_format: str = "mp4"
    bitrate: str = "2M"
    
    # 실행 시간 제한 설정
    max_recording_duration: Optional[int] = None  # 전체 녹화 시간 제한 (초)
    max_segments_per_source: Optional[int] = None  # 소스당 최대 세그먼트 수
    
    # 개별 소스별 시간 제한
    source_duration_limits: Dict[str, int] = None  # 소스별 녹화 시간 제한
    
    # 스케줄링 설정
    recording_schedule: Optional[Dict[str, any]] = None  # 녹화 스케줄
    
    # 연결 설정
    connection_timeout: int = 10000  # 연결 타임아웃 (ms)
    read_timeout: int = 5000  # 읽기 타임아웃 (ms)
    reconnect_interval: int = 5  # 재연결 간격 (초)
    
    # 프로세스 설정
    max_concurrent_recordings: int = 4  # 동시 녹화 수
    enable_monitoring: bool = True
    monitoring_interval: int = 10  # 모니터링 간격 (초)
    
    # 저장 설정
    max_disk_usage_gb: float = 100.0  # 최대 디스크 사용량 (GB)
    cleanup_old_files: bool = True  # 오래된 파일 자동 정리
    max_file_age_hours: int = 24  # 파일 최대 보관 시간

class RTSPRecorder:
    """개별 RTSP 스트림 및 로컬 영상 녹화기"""
    
    def __init__(self, source: str, config: RTSPRecorderConfig, recorder_id: int):
        self.source = source
        self.config = config
        self.recorder_id = recorder_id
        self.running = False
        
        # 소스 타입 및 이름 결정
        self.source_type = self.get_source_type(source)
        self.source_name = self.get_source_name(source)
        
        # 디렉토리 생성
        self.output_dir = Path(config.output_dir) / self.source_name
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 시간 제한 설정
        self.recording_start_time = None
        self.max_duration = self.get_max_duration_for_source()
        self.max_segments = self.get_max_segments_for_source()
        
        # 로컬 영상 관리
        self.local_video_loop_count = 0
        self.original_video_length = 0
        self.video_start_time = 0
        
        # 통계
        self.stats = {
            'segments_created': 0,
            'frames_recorded': 0,
            'bytes_written': 0,
            'errors': 0,
            'last_frame_time': None,
            'start_time': None,
            'loops_completed': 0,  # 로컬 영상 반복 횟수
            'source_type': self.source_type
        }
        
        # 현재 세그먼트 정보
        self.current_writer = None
        self.current_filepath = None
        self.segment_start_time = None
        self.segment_frame_count = 0
        self.segment_counter = 0
    
    def get_source_type(self, source: str) -> str:
        """소스 타입 결정"""
        if source.startswith(('rtsp://', 'http://', 'https://')):
            return "RTSP"
        elif os.path.exists(source):
            return "LOCAL_VIDEO"
        else:
            return "UNKNOWN"
    
    def get_source_name(self, source: str) -> str:
        """소스에서 이름 추출"""
        if source.startswith(('rtsp://', 'http://', 'https://')):
            # RTSP URL에서 이름 추출
            return f"rtsp_{abs(hash(source)) % 10000:04d}"
        else:
            # 파일 경로에서 이름 추출
            return Path(source).stem
    
    def is_rtsp_source(self, source: str) -> bool:
        """RTSP 소스인지 확인"""
        return source.startswith(('rtsp://', 'http://', 'https://'))
    
    def connect_to_source(self) -> cv2.VideoCapture:
        """소스에 연결 (RTSP 또는 로컬 영상)"""
        logger.info(f"[{self.source_name}] 소스 연결 시도: {self.source} ({self.source_type})")
        
        cap = cv2.VideoCapture(self.source)
        
        # 기본 설정
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        if self.source_type == "RTSP":
            # RTSP 전용 설정
            cap.set(cv2.CAP_PROP_FPS, self.config.input_fps)
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, self.config.connection_timeout)
            cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, self.config.read_timeout)
            
        elif self.source_type == "LOCAL_VIDEO":
            # 로컬 영상 정보 저장
            original_fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            self.original_video_length = total_frames / original_fps if original_fps > 0 else 0
            
            logger.info(f"[{self.source_name}] 로컬 영상 정보:")
            logger.info(f"  원본 FPS: {original_fps:.1f} → 목표 FPS: {self.config.input_fps}")
            logger.info(f"  총 프레임: {total_frames}")
            logger.info(f"  영상 길이: {self.original_video_length:.1f}초")
            
            # 로컬 영상은 FPS 제어를 소프트웨어적으로 처리
            self.video_start_time = time.time()
        
        if not cap.isOpened():
            raise ConnectionError(f"소스 연결 실패: {self.source}")
        
        # 연결 테스트
        ret, frame = cap.read()
        if not ret:
            cap.release()
            raise ConnectionError(f"프레임 읽기 실패: {self.source}")
        
        logger.info(f"[{self.source_name}] 소스 연결 성공 ({self.source_type})")
        return cap
    
    def should_read_frame(self) -> bool:
        """프레임을 읽을지 결정 (로컬 영상 FPS 제어)"""
        if self.source_type == "RTSP":
            # RTSP는 실시간이므로 항상 읽기
            return True
        elif self.source_type == "LOCAL_VIDEO":
            # 로컬 영상은 목표 FPS에 맞춰 제어
            current_time = time.time()
            elapsed_time = current_time - self.video_start_time
            expected_frames = elapsed_time * self.config.input_fps
            
            # 현재 읽은 프레임 수가 예상보다 적으면 읽기
            return self.stats['frames_recorded'] < expected_frames
        
        return True
    
    def handle_video_loop(self, cap: cv2.VideoCapture) -> bool:
        """로컬 영상 반복 처리"""
        if self.source_type != "LOCAL_VIDEO":
            return True
        
        # 영상 끝에 도달하면 처음으로 돌아가기
        current_pos = cap.get(cv2.CAP_PROP_POS_FRAMES)
        total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        
        if current_pos >= total_frames - 1:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            self.local_video_loop_count += 1
            self.stats['loops_completed'] += 1
            self.video_start_time = time.time()  # 시간 기준 재설정
            
            logger.info(f"[{self.source_name}] 영상 반복 재생 #{self.local_video_loop_count}")
            return True
        
        return True
        """새 세그먼트 생성"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.segment_counter += 1
        
    def create_new_segment(self, frame_width: int, frame_height: int):
        """새 세그먼트 생성"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.segment_counter += 1
        
        # 로컬 영상인 경우 루프 카운트 포함
        if self.source_type == "LOCAL_VIDEO":
            filename = f"{self.source_name}_{timestamp}_loop{self.local_video_loop_count:03d}_seg{self.segment_counter:04d}.{self.config.container_format}"
        else:
            filename = f"{self.source_name}_{timestamp}_seg{self.segment_counter:04d}.{self.config.container_format}"
        
        filepath = self.output_dir / filename
        
        # VideoWriter 생성
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(
            str(filepath),
            fourcc,
            self.config.input_fps,
            (frame_width, frame_height)
        )
        
        if not writer.isOpened():
            raise RuntimeError(f"VideoWriter 생성 실패: {filepath}")
        
        self.segment_start_time = time.time()
        self.segment_frame_count = 0
        self.current_writer = writer
        self.current_filepath = str(filepath)
        
        logger.info(f"[{self.source_name}] 새 세그먼트 생성: {filename}")
        return writer
    
    def finish_current_segment(self):
        """현재 세그먼트 완료"""
        if self.current_writer:
            self.current_writer.release()
            self.current_writer = None
            
            # 파일 정보 생성
            file_info = {
                'filepath': self.current_filepath,
                'source': self.source,
                'source_name': self.source_name,
                'recorder_id': self.recorder_id,
                'frame_count': self.segment_frame_count,
                'duration': time.time() - self.segment_start_time,
                'timestamp': datetime.now().isoformat(),
                'file_size': os.path.getsize(self.current_filepath) if os.path.exists(self.current_filepath) else 0
            }
            
            # 블러 처리 대기 큐에 추가
            self.add_to_processing_queue(file_info)
            
            # 통계 업데이트
            self.stats['segments_created'] += 1
            self.stats['bytes_written'] += file_info['file_size']
            
            logger.info(f"[{self.source_name}] 세그먼트 완료: {Path(self.current_filepath).name} "
                       f"({self.segment_frame_count} 프레임, {file_info['file_size']/1024/1024:.1f}MB)")
            
            self.current_filepath = None
    
    def add_to_processing_queue(self, file_info: Dict):
        """블러 처리 대기 큐에 파일 추가"""
        try:
            queue_dir = Path(self.config.queue_dir)
            queue_dir.mkdir(parents=True, exist_ok=True)
            
            # 큐 파일 생성
            queue_filename = f"queue_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json"
            queue_filepath = queue_dir / queue_filename
            
            with open(queue_filepath, 'w', encoding='utf-8') as f:
                json.dump(file_info, f, indent=2, ensure_ascii=False)
            
            logger.debug(f"[{self.source_name}] 큐에 추가: {queue_filename}")
            
        except Exception as e:
            logger.error(f"[{self.source_name}] 큐 추가 실패: {e}")
            self.stats['errors'] += 1
    
    def start_recording(self):
        """녹화 시작"""
        logger.info(f"[{self.source_name}] 녹화 시작 (PID: {os.getpid()}, 타입: {self.source_type})")
        
        # 녹화 시간 제한 로그
        if self.max_duration:
            logger.info(f"[{self.source_name}] 최대 녹화 시간: {self.max_duration}초")
        if self.max_segments:
            logger.info(f"[{self.source_name}] 최대 세그먼트 수: {self.max_segments}개")
        
        self.running = True
        self.stats['start_time'] = time.time()
        self.recording_start_time = time.time()
        
        cap = None
        consecutive_failures = 0
        
        while self.running:
            try:
                # 녹화 시간 초과 확인
                if self.is_recording_time_exceeded():
                    logger.info(f"[{self.source_name}] 녹화 시간 제한으로 종료")
                    break
                
                # 녹화 스케줄 확인
                if not self.is_within_recording_schedule():
                    logger.info(f"[{self.source_name}] 녹화 스케줄 외 시간, 대기 중...")
                    time.sleep(60)  # 1분 대기
                    continue
                
                # 소스 연결
                if cap is None or not cap.isOpened():
                    cap = self.connect_to_source()
                    consecutive_failures = 0
                
                # 첫 프레임으로 해상도 확인
                ret, frame = cap.read()
                if not ret:
                    logger.warning(f"[{self.source_name}] 프레임 읽기 실패")
                    
                    # 로컬 영상인 경우 루프 처리
                    if self.source_type == "LOCAL_VIDEO":
                        if self.handle_video_loop(cap):
                            continue
                    
                    consecutive_failures += 1
                    
                    if consecutive_failures > 10:
                        logger.error(f"[{self.source_name}] 연속 실패로 재연결")
                        if cap:
                            cap.release()
                        cap = None
                        time.sleep(self.config.reconnect_interval)
                        consecutive_failures = 0
                    continue
                
                # 첫 세그먼트 생성
                if self.current_writer is None:
                    frame_height, frame_width = frame.shape[:2]
                    self.create_new_segment(frame_width, frame_height)
                
                # 프레임 기록 루프
                while self.running:
                    # 녹화 시간 초과 확인
                    if self.is_recording_time_exceeded():
                        logger.info(f"[{self.source_name}] 녹화 시간 제한으로 종료")
                        self.running = False
                        break
                    
                    # 로컬 영상 FPS 제어
                    if not self.should_read_frame():
                        time.sleep(0.01)  # 짧은 대기
                        continue
                    
                    ret, frame = cap.read()
                    if not ret:
                        # 로컬 영상인 경우 루프 처리
                        if self.source_type == "LOCAL_VIDEO":
                            if self.handle_video_loop(cap):
                                continue
                        break
                    
                    # 프레임 저장
                    if self.current_writer:
                        self.current_writer.write(frame)
                        self.segment_frame_count += 1
                        self.stats['frames_recorded'] += 1
                        self.stats['last_frame_time'] = time.time()
                    
                    # 세그먼트 시간 확인
                    if (time.time() - self.segment_start_time) >= self.config.segment_duration:
                        self.finish_current_segment()
                        
                        # 세그먼트 수 제한 확인
                        if self.max_segments and self.stats['segments_created'] >= self.max_segments:
                            logger.info(f"[{self.source_name}] 최대 세그먼트 수 도달로 종료")
                            self.running = False
                            break
                        
                        # 새 세그먼트 시작
                        frame_height, frame_width = frame.shape[:2]
                        self.create_new_segment(frame_width, frame_height)
                    
                    # FPS 제어 (RTSP용)
                    if self.source_type == "RTSP":
                        time.sleep(1.0 / self.config.input_fps)
                
                consecutive_failures = 0
                
            except ConnectionError as e:
                logger.error(f"[{self.source_name}] 연결 오류: {e}")
                self.stats['errors'] += 1
                if cap:
                    cap.release()
                cap = None
                time.sleep(self.config.reconnect_interval)
                
            except Exception as e:
                logger.error(f"[{self.source_name}] 녹화 오류: {e}")
                self.stats['errors'] += 1
                time.sleep(1)
        
        # 정리
        if self.current_writer:
            self.finish_current_segment()
        
        if cap:
            cap.release()
        
        # 최종 통계
        total_duration = time.time() - self.recording_start_time if self.recording_start_time else 0
        logger.info(f"[{self.source_name}] 녹화 종료 - 총 시간: {total_duration:.1f}초, 세그먼트: {self.stats['segments_created']}개")
    
    def stop_recording(self):
        """녹화 중지"""
        logger.info(f"[{self.source_name}] 녹화 중지 요청")
        self.running = False
    
    def get_stats(self) -> Dict:
        """통계 정보 반환"""
        runtime = time.time() - self.stats['start_time'] if self.stats['start_time'] else 0
        return {
            **self.stats,
            'source': self.source,
            'source_name': self.source_name,
            'source_type': self.source_type,
            'runtime': runtime,
            'current_segment': self.current_filepath is not None,
            'fps': self.stats['frames_recorded'] / runtime if runtime > 0 else 0
        }

class RTSPRecorderManager:
    """RTSP 녹화 관리자"""
    
    def __init__(self, config: RTSPRecorderConfig):
        self.config = config
        self.running = False
        self.recorders = []
        self.recorder_threads = []
        self.monitoring_thread = None
        
        # 디렉토리 생성
        Path(config.output_dir).mkdir(parents=True, exist_ok=True)
        Path(config.queue_dir).mkdir(parents=True, exist_ok=True)
        
        # 신호 처리
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def signal_handler(self, signum, frame):
        """시그널 처리"""
        logger.info(f"시그널 {signum} 수신 - 녹화 중지")
        self.stop_all_recordings()
    
    def start_all_recordings(self):
        """모든 녹화 시작"""
        logger.info("RTSP 녹화 시스템 시작")
        self.running = True
        
        # 각 소스별 녹화기 생성 및 시작
        for i, source in enumerate(self.config.sources):
            recorder = RTSPRecorder(source, self.config, i)
            self.recorders.append(recorder)
            
            # 녹화 쓰레드 시작
            thread = threading.Thread(
                target=recorder.start_recording,
                name=f"Recorder-{i}-{recorder.source_name}",
                daemon=True
            )
            thread.start()
            self.recorder_threads.append(thread)
        
        # 모니터링 시작
        if self.config.enable_monitoring:
            self.monitoring_thread = threading.Thread(
                target=self.monitor_system,
                name="SystemMonitor",
                daemon=True
            )
            self.monitoring_thread.start()
        
        logger.info(f"총 {len(self.config.sources)}개 소스 녹화 시작")
    
    def stop_all_recordings(self):
        """모든 녹화 중지"""
        logger.info("모든 녹화 중지 시작")
        self.running = False
        
        # 모든 녹화기 중지
        for recorder in self.recorders:
            recorder.stop_recording()
        
        # 쓰레드 종료 대기
        for thread in self.recorder_threads:
            thread.join(timeout=5)
        
        logger.info("모든 녹화 중지 완료")
    
    def monitor_system(self):
        """시스템 모니터링"""
        while self.running:
            try:
                # 시스템 리소스
                cpu_percent = psutil.cpu_percent(interval=1)
                memory = psutil.virtual_memory()
                disk = psutil.disk_usage(self.config.output_dir)
                
                # 녹화기 통계 수집
                total_stats = {
                    'total_segments': 0,
                    'total_frames': 0,
                    'total_bytes': 0,
                    'total_errors': 0,
                    'active_recordings': 0
                }
                
                recorder_stats = []
                for recorder in self.recorders:
                    stats = recorder.get_stats()
                    recorder_stats.append(stats)
                    
                    total_stats['total_segments'] += stats['segments_created']
                    total_stats['total_frames'] += stats['frames_recorded']
                    total_stats['total_bytes'] += stats['bytes_written']
                    total_stats['total_errors'] += stats['errors']
                    
                    if stats['current_segment']:
                        total_stats['active_recordings'] += 1
                
                # 큐 크기 확인
                queue_size = len(list(Path(self.config.queue_dir).glob('queue_*.json')))
                
                # 로그 출력
                logger.info("=== 시스템 상태 ===")
                logger.info(f"CPU: {cpu_percent:.1f}%, 메모리: {memory.percent:.1f}%, "
                           f"디스크: {disk.percent:.1f}% ({disk.free/1024/1024/1024:.1f}GB 남음)")
                logger.info(f"활성 녹화: {total_stats['active_recordings']}/{len(self.recorders)}")
                logger.info(f"처리 대기: {queue_size}개 파일")
                logger.info(f"총 통계 - 세그먼트: {total_stats['total_segments']}, "
                           f"프레임: {total_stats['total_frames']}, "
                           f"저장: {total_stats['total_bytes']/1024/1024:.1f}MB, "
                           f"오류: {total_stats['total_errors']}")
                
                # 녹화기별 상세 통계
                for stats in recorder_stats:
                    if stats['runtime'] > 0:
                        source_type_indicator = "📹" if stats['source_type'] == "RTSP" else "🎬"
                        loop_info = f", 반복: {stats['loops_completed']}회" if stats['source_type'] == "LOCAL_VIDEO" else ""
                        
                        logger.info(f"{source_type_indicator} [{stats['source_name']}] "
                                   f"세그먼트: {stats['segments_created']}, "
                                   f"FPS: {stats['fps']:.1f}, "
                                   f"실행시간: {stats['runtime']:.0f}초{loop_info}")
                
                # 디스크 사용량 체크
                if disk.percent > 90:
                    logger.warning("디스크 사용량이 90%를 초과했습니다!")
                
                time.sleep(self.config.monitoring_interval)
                
            except Exception as e:
                logger.error(f"모니터링 오류: {e}")
                time.sleep(self.config.monitoring_interval)
    
    def cleanup_old_files(self):
        """오래된 파일 정리"""
        if not self.config.cleanup_old_files:
            return
        
        try:
            current_time = time.time()
            max_age = self.config.max_file_age_hours * 3600
            
            for file_path in Path(self.config.output_dir).rglob('*.mp4'):
                file_age = current_time - file_path.stat().st_mtime
                if file_age > max_age:
                    file_path.unlink()
                    logger.info(f"오래된 파일 삭제: {file_path.name}")
                    
        except Exception as e:
            logger.error(f"파일 정리 오류: {e}")

def load_config(config_path: str) -> RTSPRecorderConfig:
    """설정 파일 로드"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        
        return RTSPRecorderConfig(**config_data)
    except Exception as e:
        logger.error(f"설정 파일 로드 실패: {e}")
        raise

def create_default_config(config_path: str):
    """기본 설정 파일 생성"""
    default_config = RTSPRecorderConfig(
        sources=[
            # RTSP 카메라 예제
            "rtsp://admin:password@192.168.1.100:554/stream",
            "rtsp://admin:password@192.168.1.101:554/stream",
            
            # 로컬 영상 파일 예제
            "./videos/sample_video1.mp4",
            "./videos/sample_video2.mp4",
            
            # 혼합 사용 가능
            # "rtsp://192.168.1.102:554/live",
            # "./test_videos/traffic.mp4"
        ],
        output_dir="./raw_videos",
        queue_dir="./processing_queue",
        segment_duration=30,
        input_fps=15.0,
        max_concurrent_recordings=4,
        enable_monitoring=True,
        monitoring_interval=10,
        
        # 시간 제한 설정 예제
        max_recording_duration=3600,  # 1시간 (3600초)
        max_segments_per_source=120,  # 소스당 최대 120개 세그먼트
        
        # 개별 소스별 시간 제한 예제
        source_duration_limits={
            "rtsp://admin:password@192.168.1.100:554/stream": 1800,  # 30분
            "./videos/sample_video1.mp4": 900,  # 15분
        },
        
        # 녹화 스케줄 예제 (평일 오전 9시 ~ 오후 6시)
        recording_schedule={
            "weekdays": [0, 1, 2, 3, 4],  # 월~금 (0=월요일, 6=일요일)
            "start_time": "09:00",
            "end_time": "18:00"
        }
    )
    
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(asdict(default_config), f, indent=2, ensure_ascii=False)
    
    logger.info(f"기본 설정 파일 생성: {config_path}")
    logger.info("설정 파일에서 sources를 실제 RTSP URL이나 로컬 영상 파일 경로로 수정하세요")
    logger.info("시간 제한 설정도 필요에 따라 수정하세요")

def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description='RTSP 영상 저장 프로세스')
    parser.add_argument('--config', '-c', default='rtsp_recorder_config.json',
                       help='설정 파일 경로')
    parser.add_argument('--create-config', action='store_true',
                       help='기본 설정 파일 생성')
    
    args = parser.parse_args()
    
    # 기본 설정 파일 생성
    if args.create_config:
        create_default_config(args.config)
        return
    
    # 설정 파일 로드
    if not os.path.exists(args.config):
        logger.error(f"설정 파일이 없습니다: {args.config}")
        logger.info("--create-config 옵션으로 기본 설정 파일을 생성하세요")
        return
    
    try:
        config = load_config(args.config)
        logger.info(f"설정 파일 로드: {args.config}")
        
        # 녹화 관리자 생성 및 시작
        manager = RTSPRecorderManager(config)
        manager.start_all_recordings()
        
        # 무한 실행 (시그널로 중지)
        while manager.running:
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("사용자 중지 요청")
    except Exception as e:
        logger.error(f"실행 오류: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())