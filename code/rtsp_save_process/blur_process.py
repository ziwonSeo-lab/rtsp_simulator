"""
블러 처리 프로세스
- 저장된 원본 영상에 블러 처리 적용
- 처리 완료 후 원본 파일 삭제
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
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, List
from dataclasses import dataclass, asdict
import importlib.util
import psutil
import shutil
import glob

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [BLUR_PROCESSOR] - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class BlurProcessorConfig:
    """블러 처리 설정"""
    queue_dir: str = "./processing_queue"  # 처리 대기 큐 디렉토리
    output_dir: str = "./processed_videos"  # 처리된 영상 저장 경로
    blur_module_path: Optional[str] = None  # 블러 모듈 경로
    
    # 처리 설정
    max_concurrent_processes: int = 2  # 동시 처리 프로세스 수
    polling_interval: float = 1.0  # 큐 폴링 간격 (초)
    process_timeout: int = 300  # 처리 타임아웃 (초)
    
    # 블러 처리 설정
    blur_strength: int = 15  # 기본 블러 강도
    blur_kernel_size: int = 15  # 블러 커널 크기
    
    # 파일 관리
    delete_original: bool = True  # 원본 파일 삭제 여부
    backup_original: bool = False  # 원본 파일 백업 여부
    backup_dir: str = "./backup_videos"  # 백업 디렉토리
    
    # 시스템 설정
    enable_monitoring: bool = True
    monitoring_interval: int = 10
    max_queue_size: int = 100  # 최대 큐 크기
    
    # 영상 처리 설정
    resize_before_blur: bool = False  # 블러 전 리사이즈 여부
    resize_width: int = 640  # 리사이즈 폭
    resize_height: int = 480  # 리사이즈 높이
    
    # 오버레이 설정
    add_overlay: bool = True  # 처리 정보 오버레이 추가
    overlay_text: str = "BLUR_PROCESSED"  # 오버레이 텍스트

class BlurModule:
    """블러 모듈 래퍼"""
    
    def __init__(self, config: BlurProcessorConfig):
        self.config = config
        self.user_module = None
        self.load_blur_module()
    
    def load_blur_module(self):
        """사용자 블러 모듈 로드"""
        if not self.config.blur_module_path:
            logger.info("블러 모듈 경로가 설정되지 않음. 기본 블러 사용")
            return
        
        if not os.path.exists(self.config.blur_module_path):
            logger.warning(f"블러 모듈 파일이 존재하지 않음: {self.config.blur_module_path}")
            return
        
        try:
            spec = importlib.util.spec_from_file_location("user_blur_module", self.config.blur_module_path)
            blur_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(blur_module)
            
            if hasattr(blur_module, 'HeadBlurrer'):
                self.user_module = blur_module.HeadBlurrer(num_camera=1)
                logger.info("HeadBlurrer 모듈 로드 성공")
            elif hasattr(blur_module, 'apply_blur'):
                self.user_module = blur_module
                logger.info("apply_blur 함수 모듈 로드 성공")
            else:
                logger.error("블러 모듈에 'HeadBlurrer' 클래스나 'apply_blur' 함수가 없음")
                self.user_module = None
                
        except Exception as e:
            logger.error(f"블러 모듈 로드 실패: {e}")
            self.user_module = None
    
    def apply_blur(self, frame):
        """블러 적용"""
        if self.user_module is None:
            # 기본 블러 처리
            return cv2.GaussianBlur(frame, (self.config.blur_kernel_size, self.config.blur_kernel_size), 0)
        
        try:
            if hasattr(self.user_module, 'process_frame'):
                return self.user_module.process_frame(frame, 0)
            elif hasattr(self.user_module, 'apply_blur'):
                return self.user_module.apply_blur(frame)
            else:
                return cv2.GaussianBlur(frame, (self.config.blur_kernel_size, self.config.blur_kernel_size), 0)
                
        except Exception as e:
            logger.error(f"사용자 블러 처리 오류: {e}")
            # 폴백: 기본 블러 사용
            return cv2.GaussianBlur(frame, (self.config.blur_kernel_size, self.config.blur_kernel_size), 0)

class VideoBlurProcessor:
    """개별 비디오 블러 처리기"""
    
    def __init__(self, config: BlurProcessorConfig, processor_id: int):
        self.config = config
        self.processor_id = processor_id
        self.blur_module = BlurModule(config)
        
        # 통계
        self.stats = {
            'videos_processed': 0,
            'frames_processed': 0,
            'processing_time': 0,
            'errors': 0,
            'start_time': time.time()
        }
    
    def add_overlay(self, frame, info_text: str):
        """오버레이 추가"""
        if not self.config.add_overlay:
            return frame
        
        try:
            # 현재 시간
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 오버레이 텍스트들
            overlay_lines = [
                f"{self.config.overlay_text}",
                f"Time: {current_time}",
                f"Processor: {self.processor_id}",
                info_text
            ]
            
            # 반투명 배경
            overlay_height = len(overlay_lines) * 25 + 10
            overlay_width = 400
            
            overlay = frame.copy()
            cv2.rectangle(overlay, (5, 5), (overlay_width, overlay_height), (0, 0, 0), -1)
            cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
            
            # 텍스트 추가
            for i, line in enumerate(overlay_lines):
                y_pos = 25 + i * 25
                cv2.putText(frame, line, (10, y_pos), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 1, cv2.LINE_AA)
            
            return frame
            
        except Exception as e:
            logger.error(f"오버레이 추가 오류: {e}")
            return frame
    
    def process_video_file(self, file_info: Dict) -> bool:
        """비디오 파일 블러 처리"""
        input_path = file_info['filepath']
        source_name = file_info['source_name']
        
        logger.info(f"[P{self.processor_id}] 블러 처리 시작: {Path(input_path).name}")
        
        # 입력 파일 확인
        if not os.path.exists(input_path):
            logger.error(f"[P{self.processor_id}] 입력 파일이 존재하지 않음: {input_path}")
            return False
        
        # 출력 경로 생성
        output_dir = Path(self.config.output_dir) / source_name
        output_dir.mkdir(parents=True, exist_ok=True)
        
        input_file = Path(input_path)
        output_filename = f"blurred_{input_file.name}"
        output_path = output_dir / output_filename
        
        cap = None
        writer = None
        processing_start_time = time.time()
        
        try:
            # 입력 비디오 열기
            cap = cv2.VideoCapture(input_path)
            if not cap.isOpened():
                raise RuntimeError(f"입력 비디오 열기 실패: {input_path}")
            
            # 비디오 속성 가져오기
            fps = cap.get(cv2.CAP_PROP_FPS)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            logger.info(f"[P{self.processor_id}] 입력 비디오 정보: {width}x{height}, {fps}fps, {total_frames}프레임")
            
            # 리사이즈 설정
            if self.config.resize_before_blur:
                output_width = self.config.resize_width
                output_height = self.config.resize_height
            else:
                output_width = width
                output_height = height
            
            # 출력 비디오 writer 생성
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            writer = cv2.VideoWriter(str(output_path), fourcc, fps, (output_width, output_height))
            
            if not writer.isOpened():
                raise RuntimeError(f"출력 비디오 writer 생성 실패: {output_path}")
            
            # 프레임별 처리
            frame_count = 0
            processed_frames = 0
            
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                
                # 리사이즈 (필요한 경우)
                if self.config.resize_before_blur:
                    frame = cv2.resize(frame, (output_width, output_height))
                
                # 블러 처리
                blurred_frame = self.blur_module.apply_blur(frame)
                
                # 오버레이 추가
                info_text = f"Frame: {frame_count + 1}/{total_frames}"
                final_frame = self.add_overlay(blurred_frame, info_text)
                
                # 프레임 쓰기
                writer.write(final_frame)
                
                frame_count += 1
                processed_frames += 1
                
                # 진행률 로그 (100 프레임마다)
                if frame_count % 100 == 0:
                    progress = (frame_count / total_frames) * 100 if total_frames > 0 else 0
                    logger.info(f"[P{self.processor_id}] 진행률: {progress:.1f}% ({frame_count}/{total_frames})")
            
            processing_time = time.time() - processing_start_time
            
            # 통계 업데이트
            self.stats['videos_processed'] += 1
            self.stats['frames_processed'] += processed_frames
            self.stats['processing_time'] += processing_time
            
            logger.info(f"[P{self.processor_id}] 블러 처리 완료: {output_filename} "
                       f"({processed_frames}프레임, {processing_time:.1f}초)")
            
            return True
            
        except Exception as e:
            logger.error(f"[P{self.processor_id}] 블러 처리 오류: {e}")
            self.stats['errors'] += 1
            return False
        
        finally:
            if cap:
                cap.release()
            if writer:
                writer.release()
    
    def handle_file_cleanup(self, file_info: Dict, processing_success: bool):
        """파일 정리 처리"""
        input_path = file_info['filepath']
        
        if not processing_success:
            logger.error(f"[P{self.processor_id}] 처리 실패로 원본 파일 유지: {Path(input_path).name}")
            return
        
        try:
            # 백업 처리
            if self.config.backup_original:
                backup_dir = Path(self.config.backup_dir) / file_info['source_name']
                backup_dir.mkdir(parents=True, exist_ok=True)
                
                backup_path = backup_dir / Path(input_path).name
                shutil.copy2(input_path, backup_path)
                logger.info(f"[P{self.processor_id}] 원본 파일 백업: {backup_path}")
            
            # 원본 파일 삭제
            if self.config.delete_original:
                os.remove(input_path)
                logger.info(f"[P{self.processor_id}] 원본 파일 삭제: {Path(input_path).name}")
            
        except Exception as e:
            logger.error(f"[P{self.processor_id}] 파일 정리 오류: {e}")
    
    def get_stats(self) -> Dict:
        """통계 정보 반환"""
        runtime = time.time() - self.stats['start_time']
        return {
            **self.stats,
            'processor_id': self.processor_id,
            'runtime': runtime,
            'processing_rate': self.stats['frames_processed'] / runtime if runtime > 0 else 0
        }

class BlurProcessorManager:
    """블러 처리 관리자"""
    
    def __init__(self, config: BlurProcessorConfig):
        self.config = config
        self.running = False
        self.processors = []
        self.processor_threads = []
        self.monitoring_thread = None
        self.queue_monitor_thread = None
        
        # 디렉토리 생성
        Path(config.output_dir).mkdir(parents=True, exist_ok=True)
        if config.backup_original:
            Path(config.backup_dir).mkdir(parents=True, exist_ok=True)
        
        # 신호 처리
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def signal_handler(self, signum, frame):
        """시그널 처리"""
        logger.info(f"시그널 {signum} 수신 - 처리 중지")
        self.stop_processing()
    
    def get_queue_files(self) -> List[str]:
        """큐 파일 목록 반환"""
        queue_pattern = os.path.join(self.config.queue_dir, "queue_*.json")
        return sorted(glob.glob(queue_pattern))
    
    def process_queue_file(self, queue_file: str, processor: VideoBlurProcessor) -> bool:
        """큐 파일 처리"""
        try:
            # 큐 파일 읽기
            with open(queue_file, 'r', encoding='utf-8') as f:
                file_info = json.load(f)
            
            # 비디오 처리
            success = processor.process_video_file(file_info)
            
            # 파일 정리
            processor.handle_file_cleanup(file_info, success)
            
            # 큐 파일 삭제
            os.remove(queue_file)
            
            return success
            
        except Exception as e:
            logger.error(f"큐 파일 처리 오류: {e}")
            return False
    
    def processor_worker(self, processor_id: int):
        """처리기 워커"""
        processor = VideoBlurProcessor(self.config, processor_id)
        self.processors.append(processor)
        
        logger.info(f"[P{processor_id}] 블러 처리기 시작")
        
        while self.running:
            try:
                # 큐에서 처리할 파일 찾기
                queue_files = self.get_queue_files()
                
                if not queue_files:
                    time.sleep(self.config.polling_interval)
                    continue
                
                # 첫 번째 파일 처리
                queue_file = queue_files[0]
                logger.info(f"[P{processor_id}] 처리 시작: {Path(queue_file).name}")
                
                success = self.process_queue_file(queue_file, processor)
                
                if success:
                    logger.info(f"[P{processor_id}] 처리 완료: {Path(queue_file).name}")
                else:
                    logger.error(f"[P{processor_id}] 처리 실패: {Path(queue_file).name}")
                
            except Exception as e:
                logger.error(f"[P{processor_id}] 워커 오류: {e}")
                time.sleep(self.config.polling_interval)
        
        logger.info(f"[P{processor_id}] 블러 처리기 종료")
    
    def start_processing(self):
        """처리 시작"""
        logger.info("블러 처리 시스템 시작")
        self.running = True
        
        # 처리기 워커 시작
        for i in range(self.config.max_concurrent_processes):
            thread = threading.Thread(
                target=self.processor_worker,
                args=(i,),
                name=f"BlurProcessor-{i}",
                daemon=True
            )
            thread.start()
            self.processor_threads.append(thread)
        
        # 모니터링 시작
        if self.config.enable_monitoring:
            self.monitoring_thread = threading.Thread(
                target=self.monitor_system,
                name="BlurMonitor",
                daemon=True
            )
            self.monitoring_thread.start()
        
        logger.info(f"블러 처리기 {self.config.max_concurrent_processes}개 시작")
    
    def stop_processing(self):
        """처리 중지"""
        logger.info("블러 처리 중지 시작")
        self.running = False
        
        # 모든 쓰레드 종료 대기
        for thread in self.processor_threads:
            thread.join(timeout=5)
        
        logger.info("블러 처리 중지 완료")
    
    def monitor_system(self):
        """시스템 모니터링"""
        while self.running:
            try:
                # 시스템 리소스
                cpu_percent = psutil.cpu_percent(interval=1)
                memory = psutil.virtual_memory()
                
                # 큐 상태
                queue_files = self.get_queue_files()
                queue_size = len(queue_files)
                
                # 처리기 통계
                total_stats = {
                    'videos_processed': 0,
                    'frames_processed': 0,
                    'processing_time': 0,
                    'errors': 0
                }
                
                active_processors = 0
                for processor in self.processors:
                    stats = processor.get_stats()
                    total_stats['videos_processed'] += stats['videos_processed']
                    total_stats['frames_processed'] += stats['frames_processed']
                    total_stats['processing_time'] += stats['processing_time']
                    total_stats['errors'] += stats['errors']
                    active_processors += 1
                
                # 로그 출력
                logger.info("=== 블러 처리 시스템 상태 ===")
                logger.info(f"CPU: {cpu_percent:.1f}%, 메모리: {memory.percent:.1f}%")
                logger.info(f"처리 대기: {queue_size}개 파일")
                logger.info(f"활성 처리기: {active_processors}/{self.config.max_concurrent_processes}")
                logger.info(f"처리 통계 - 비디오: {total_stats['videos_processed']}, "
                           f"프레임: {total_stats['frames_processed']}, "
                           f"시간: {total_stats['processing_time']:.1f}초, "
                           f"오류: {total_stats['errors']}")
                
                # 처리기별 상세 통계
                for processor in self.processors:
                    stats = processor.get_stats()
                    if stats['videos_processed'] > 0:
                        logger.info(f"[P{stats['processor_id']}] "
                                   f"처리: {stats['videos_processed']}개, "
                                   f"속도: {stats['processing_rate']:.1f}fps")
                
                # 큐 크기 경고
                if queue_size > self.config.max_queue_size:
                    logger.warning(f"큐 크기가 임계값을 초과했습니다: {queue_size}/{self.config.max_queue_size}")
                
                time.sleep(self.config.monitoring_interval)
                
            except Exception as e:
                logger.error(f"모니터링 오류: {e}")
                time.sleep(self.config.monitoring_interval)

def load_config(config_path: str) -> BlurProcessorConfig:
    """설정 파일 로드"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        
        return BlurProcessorConfig(**config_data)
    except Exception as e:
        logger.error(f"설정 파일 로드 실패: {e}")
        raise

def create_default_config(config_path: str):
    """기본 설정 파일 생성"""
    default_config = BlurProcessorConfig(
        queue_dir="./processing_queue",
        output_dir="./processed_videos",
        blur_module_path="./blur_module.py",
        max_concurrent_processes=2,
        polling_interval=1.0,
        delete_original=True,
        backup_original=False,
        add_overlay=True,
        enable_monitoring=True,
        monitoring_interval=10
    )
    
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(asdict(default_config), f, indent=2, ensure_ascii=False)
    
    logger.info(f"기본 설정 파일 생성: {config_path}")

def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description='블러 처리 프로세스')
    parser.add_argument('--config', '-c', default='blur_processor_config.json',
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
        
        # 블러 처리 관리자 생성 및 시작
        manager = BlurProcessorManager(config)
        manager.start_processing()
        
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