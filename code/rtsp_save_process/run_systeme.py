"""
RTSP 영상 처리 시스템 실행 스크립트
- RTSP 녹화 프로세스와 블러 처리 프로세스를 동시에 실행
- 각 프로세스를 독립적으로 관리
"""

import os
import sys
import time
import json
import signal
import logging
import argparse
import subprocess
import threading
from pathlib import Path
from typing import Dict, List, Optional
import psutil

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [SYSTEM] - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SystemManager:
    """시스템 관리자"""
    
    def __init__(self, recorder_config: str, blur_config: str):
        self.recorder_config = recorder_config
        self.blur_config = blur_config
        self.running = False
        
        # 프로세스 관리
        self.recorder_process = None
        self.blur_process = None
        
        # 모니터링
        self.monitor_thread = None
        self.stats = {
            'start_time': None,
            'recorder_restarts': 0,
            'blur_restarts': 0,
            'total_uptime': 0
        }
        
        # 신호 처리
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def signal_handler(self, signum, frame):
        """시그널 처리"""
        logger.info(f"시그널 {signum} 수신 - 시스템 종료")
        self.stop_system()
    
    def start_recorder_process(self):
        """RTSP 녹화 프로세스 시작"""
        try:
            cmd = [sys.executable, 'rtsp_recorder.py', '--config', self.recorder_config]
            
            self.recorder_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
            
            logger.info(f"RTSP 녹화 프로세스 시작 (PID: {self.recorder_process.pid})")
            
            # 출력 로그 스레드 시작
            log_thread = threading.Thread(
                target=self.log_process_output,
                args=(self.recorder_process, "RECORDER"),
                daemon=True
            )
            log_thread.start()
            
            return True
            
        except Exception as e:
            logger.error(f"RTSP 녹화 프로세스 시작 실패: {e}")
            return False
    
    def start_blur_process(self):
        """블러 처리 프로세스 시작"""
        try:
            cmd = [sys.executable, 'blur_processor.py', '--config', self.blur_config]
            
            self.blur_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
            
            logger.info(f"블러 처리 프로세스 시작 (PID: {self.blur_process.pid})")
            
            # 출력 로그 스레드 시작
            log_thread = threading.Thread(
                target=self.log_process_output,
                args=(self.blur_process, "BLUR"),
                daemon=True
            )
            log_thread.start()
            
            return True
            
        except Exception as e:
            logger.error(f"블러 처리 프로세스 시작 실패: {e}")
            return False
    
    def log_process_output(self, process: subprocess.Popen, process_name: str):
        """프로세스 출력 로그"""
        try:
            while process.poll() is None:
                line = process.stdout.readline()
                if line:
                    logger.info(f"[{process_name}] {line.strip()}")
        except Exception as e:
            logger.error(f"[{process_name}] 로그 출력 오류: {e}")
    
    def is_process_running(self, process: subprocess.Popen) -> bool:
        """프로세스 실행 상태 확인"""
        if process is None:
            return False
        return process.poll() is None
    
    def restart_recorder_process(self):
        """RTSP 녹화 프로세스 재시작"""
        logger.warning("RTSP 녹화 프로세스 재시작")
        
        if self.recorder_process:
            try:
                self.recorder_process.terminate()
                self.recorder_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.recorder_process.kill()
            except Exception as e:
                logger.error(f"녹화 프로세스 종료 오류: {e}")
        
        # 재시작
        if self.start_recorder_process():
            self.stats['recorder_restarts'] += 1
            logger.info("RTSP 녹화 프로세스 재시작 완료")
        else:
            logger.error("RTSP 녹화 프로세스 재시작 실패")
    
    def restart_blur_process(self):
        """블러 처리 프로세스 재시작"""
        logger.warning("블러 처리 프로세스 재시작")
        
        if self.blur_process:
            try:
                self.blur_process.terminate()
                self.blur_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.blur_process.kill()
            except Exception as e:
                logger.error(f"블러 프로세스 종료 오류: {e}")
        
        # 재시작
        if self.start_blur_process():
            self.stats['blur_restarts'] += 1
            logger.info("블러 처리 프로세스 재시작 완료")
        else:
            logger.error("블러 처리 프로세스 재시작 실패")
    
    def monitor_processes(self):
        """프로세스 모니터링"""
        while self.running:
            try:
                # RTSP 녹화 프로세스 확인
                if not self.is_process_running(self.recorder_process):
                    logger.error("RTSP 녹화 프로세스가 중지됨")
                    self.restart_recorder_process()
                
                # 블러 처리 프로세스 확인
                if not self.is_process_running(self.blur_process):
                    logger.error("블러 처리 프로세스가 중지됨")
                    self.restart_blur_process()
                
                # 시스템 상태 로그
                self.log_system_status()
                
                time.sleep(30)  # 30초마다 확인
                
            except Exception as e:
                logger.error(f"프로세스 모니터링 오류: {e}")
                time.sleep(30)
    
    def log_system_status(self):
        """시스템 상태 로그"""
        try:
            # 실행 시간 계산
            runtime = time.time() - self.stats['start_time'] if self.stats['start_time'] else 0
            
            # 프로세스 상태
            recorder_status = "실행 중" if self.is_process_running(self.recorder_process) else "중지됨"
            blur_status = "실행 중" if self.is_process_running(self.blur_process) else "중지됨"
            
            # 시스템 리소스
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            
            # 큐 상태 확인
            queue_dir = Path("./processing_queue")
            queue_size = len(list(queue_dir.glob("queue_*.json"))) if queue_dir.exists() else 0
            
            # 디렉토리 크기 확인
            raw_dir = Path("./raw_videos")
            processed_dir = Path("./processed_videos")
            
            raw_size = self.get_directory_size(raw_dir)
            processed_size = self.get_directory_size(processed_dir)
            
            logger.info("=== 시스템 상태 ===")
            logger.info(f"실행 시간: {runtime:.0f}초")
            logger.info(f"RTSP 녹화: {recorder_status}, 블러 처리: {blur_status}")
            logger.info(f"재시작 횟수 - 녹화: {self.stats['recorder_restarts']}, 블러: {self.stats['blur_restarts']}")
            logger.info(f"CPU: {cpu_percent:.1f}%, 메모리: {memory.percent:.1f}%")
            logger.info(f"처리 대기: {queue_size}개 파일")
            logger.info(f"저장 용량 - 원본: {raw_size:.1f}GB, 처리: {processed_size:.1f}GB")
            
        except Exception as e:
            logger.error(f"시스템 상태 로그 오류: {e}")
    
    def get_directory_size(self, directory: Path) -> float:
        """디렉토리 크기 계산 (GB)"""
        try:
            if not directory.exists():
                return 0.0
            
            total_size = 0
            for file_path in directory.rglob('*'):
                if file_path.is_file():
                    total_size += file_path.stat().st_size
            
            return total_size / (1024 ** 3)  # GB로 변환
            
        except Exception as e:
            logger.error(f"디렉토리 크기 계산 오류: {e}")
            return 0.0
    
    def start_system(self):
        """시스템 시작"""
        logger.info("RTSP 영상 처리 시스템 시작")
        self.running = True
        self.stats['start_time'] = time.time()
        
        # 필수 디렉토리 생성
        for dir_path in ["./raw_videos", "./processed_videos", "./processing_queue"]:
            Path(dir_path).mkdir(parents=True, exist_ok=True)
        
        # 설정 파일 확인
        if not os.path.exists(self.recorder_config):
            logger.error(f"RTSP 녹화 설정 파일이 없습니다: {self.recorder_config}")
            return False
        
        if not os.path.exists(self.blur_config):
            logger.error(f"블러 처리 설정 파일이 없습니다: {self.blur_config}")
            return False
        
        # 프로세스 시작
        success = True
        
        if not self.start_recorder_process():
            success = False
        
        if not self.start_blur_process():
            success = False
        
        if not success:
            logger.error("일부 프로세스 시작 실패")
            self.stop_system()
            return False
        
        # 모니터링 스레드 시작
        self.monitor_thread = threading.Thread(
            target=self.monitor_processes,
            name="SystemMonitor",
            daemon=True
        )
        self.monitor_thread.start()
        
        logger.info("시스템 시작 완료")
        return True
    
    def stop_system(self):
        """시스템 중지"""
        logger.info("시스템 중지 시작")
        self.running = False
        
        # RTSP 녹화 프로세스 중지
        if self.recorder_process:
            try:
                logger.info("RTSP 녹화 프로세스 중지")
                self.recorder_process.terminate()
                self.recorder_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.warning("RTSP 녹화 프로세스 강제 종료")
                self.recorder_process.kill()
            except Exception as e:
                logger.error(f"RTSP 녹화 프로세스 종료 오류: {e}")
        
        # 블러 처리 프로세스 중지
        if self.blur_process:
            try:
                logger.info("블러 처리 프로세스 중지")
                self.blur_process.terminate()
                self.blur_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.warning("블러 처리 프로세스 강제 종료")
                self.blur_process.kill()
            except Exception as e:
                logger.error(f"블러 처리 프로세스 종료 오류: {e}")
        
        # 최종 통계 출력
        self.log_final_stats()
        
        logger.info("시스템 중지 완료")
    
    def log_final_stats(self):
        """최종 통계 출력"""
        try:
            runtime = time.time() - self.stats['start_time'] if self.stats['start_time'] else 0
            
            logger.info("=== 최종 통계 ===")
            logger.info(f"총 실행 시간: {runtime:.0f}초")
            logger.info(f"재시작 횟수 - 녹화: {self.stats['recorder_restarts']}, 블러: {self.stats['blur_restarts']}")
            
            # 디렉토리 크기
            raw_size = self.get_directory_size(Path("./raw_videos"))
            processed_size = self.get_directory_size(Path("./processed_videos"))
            
            logger.info(f"최종 저장 용량 - 원본: {raw_size:.1f}GB, 처리: {processed_size:.1f}GB")
            
        except Exception as e:
            logger.error(f"최종 통계 오류: {e}")
    
    def get_system_info(self) -> Dict:
        """시스템 정보 반환"""
        return {
            'running': self.running,
            'recorder_running': self.is_process_running(self.recorder_process),
            'blur_running': self.is_process_running(self.blur_process),
            'stats': self.stats.copy(),
            'runtime': time.time() - self.stats['start_time'] if self.stats['start_time'] else 0
        }

def create_default_configs():
    """기본 설정 파일들 생성"""
    # RTSP 녹화 설정
    if not os.path.exists('rtsp_recorder_config.json'):
        subprocess.run([sys.executable, 'rtsp_recorder.py', '--create-config'])
    
    # 블러 처리 설정
    if not os.path.exists('blur_processor_config.json'):
        subprocess.run([sys.executable, 'blur_processor.py', '--create-config'])
    
    logger.info("기본 설정 파일 생성 완료")

def validate_system():
    """시스템 검증"""
    logger.info("시스템 검증 시작")
    
    # 필수 파일 확인
    required_files = [
        'rtsp_recorder.py',
        'blur_processor.py'
    ]
    
    for file_path in required_files:
        if not os.path.exists(file_path):
            logger.error(f"필수 파일이 없습니다: {file_path}")
            return False
    
    # Python 패키지 확인
    try:
        import cv2
        import psutil
        logger.info("필수 패키지 확인 완료")
    except ImportError as e:
        logger.error(f"필수 패키지가 없습니다: {e}")
        return False
    
    # 디렉토리 생성
    for dir_path in ["./raw_videos", "./processed_videos", "./processing_queue", "./logs"]:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
    
    logger.info("시스템 검증 완료")
    return True

def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description='RTSP 영상 처리 시스템')
    parser.add_argument('--recorder-config', default='rtsp_recorder_config.json',
                       help='RTSP 녹화 설정 파일')
    parser.add_argument('--blur-config', default='blur_processor_config.json',
                       help='블러 처리 설정 파일')
    parser.add_argument('--create-configs', action='store_true',
                       help='기본 설정 파일 생성')
    parser.add_argument('--validate', action='store_true',
                       help='시스템 검증만 실행')
    parser.add_argument('--duration', type=int, default=0,
                       help='실행 시간 제한 (초, 0=무제한)')
    
    args = parser.parse_args()
    
    # 기본 설정 파일 생성
    if args.create_configs:
        create_default_configs()
        return 0
    
    # 시스템 검증
    if args.validate:
        return 0 if validate_system() else 1
    
    # 시스템 검증 실행
    if not validate_system():
        return 1
    
    # 설정 파일 확인
    if not os.path.exists(args.recorder_config):
        logger.error(f"RTSP 녹화 설정 파일이 없습니다: {args.recorder_config}")
        logger.info("--create-configs 옵션으로 기본 설정을 생성하세요")
        return 1
    
    if not os.path.exists(args.blur_config):
        logger.error(f"블러 처리 설정 파일이 없습니다: {args.blur_config}")
        logger.info("--create-configs 옵션으로 기본 설정을 생성하세요")
        return 1
    
    try:
        # 시스템 관리자 생성
        manager = SystemManager(args.recorder_config, args.blur_config)
        
        # 시스템 시작
        if not manager.start_system():
            logger.error("시스템 시작 실패")
            return 1
        
        # 실행 시간 제한이 있는 경우
        if args.duration > 0:
            logger.info(f"시스템이 {args.duration}초 동안 실행됩니다")
            time.sleep(args.duration)
        else:
            # 무한 실행 (시그널로 중지)
            logger.info("시스템이 실행 중입니다 (Ctrl+C로 중지)")
            while manager.running:
                time.sleep(1)
        
    except KeyboardInterrupt:
        logger.info("사용자 중지 요청")
    except Exception as e:
        logger.error(f"시스템 실행 오류: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())