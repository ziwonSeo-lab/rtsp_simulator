#!/usr/bin/env python3
"""
RTSP 영상 파일 자동 이동 스크립트
watchdog를 사용하여 temp_ 접두사가 제거된 완료된 영상 파일을
최종 저장 경로(/mnt/raid5/YYYY/MM/DD/HH/)로 자동 이동
"""

import os
import sys
import shutil
import logging
import signal
import time
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
import threading

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:
    print("❌ watchdog 패키지가 설치되지 않았습니다. pip install watchdog로 설치하세요.")
    sys.exit(1)

from config import get_env_value

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('file_mover.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class VideoFileMoveHandler(FileSystemEventHandler):
    """영상 파일 이동 처리 핸들러"""
    
    def __init__(self, temp_path: str, final_path: str):
        self.temp_path = Path(temp_path)
        self.final_path = Path(final_path)
        self.processing_files = set()  # 처리 중인 파일들 추적
        
        logger.info(f"파일 모니터링 시작:")
        logger.info(f"  📁 임시 경로: {self.temp_path}")
        logger.info(f"  📁 최종 경로: {self.final_path}")
        
        # 최종 경로 생성
        self.final_path.mkdir(parents=True, exist_ok=True)
    
    def on_moved(self, event):
        """파일 이름 변경(temp_ 제거) 감지"""
        if event.is_directory:
            return
        
        # temp_ -> 일반 파일명으로 변경된 경우만 처리
        if (event.src_path.endswith('.mp4') and 
            'temp_' in os.path.basename(event.src_path) and
            not os.path.basename(event.dest_path).startswith('temp_')):
            
            self._process_completed_file(event.dest_path)
    
    def on_created(self, event):
        """새 파일 생성 감지 (temp_ 접두사 없는 경우)"""
        if event.is_directory:
            return
        
        if (event.src_path.endswith('.mp4') and 
            not os.path.basename(event.src_path).startswith('temp_')):
            
            # 파일이 완전히 생성될 때까지 잠시 대기
            threading.Timer(2.0, self._process_completed_file, args=[event.src_path]).start()
    
    def _process_completed_file(self, file_path: str):
        """완료된 영상 파일 처리"""
        file_path = Path(file_path)
        
        # 중복 처리 방지
        if str(file_path) in self.processing_files:
            return
        
        # 파일이 실제로 존재하는지 확인
        if not file_path.exists():
            logger.warning(f"파일이 존재하지 않음: {file_path}")
            return
        
        self.processing_files.add(str(file_path))
        
        try:
            logger.info(f"🎬 완료된 영상 파일 발견: {file_path.name}")
            
            # 파일명에서 시간 정보 추출
            target_dir = self._extract_time_based_directory(file_path.name)
            if not target_dir:
                logger.error(f"파일명에서 시간 정보를 추출할 수 없음: {file_path.name}")
                return
            
            # 최종 저장 경로 생성
            final_dir = self.final_path / target_dir
            final_dir.mkdir(parents=True, exist_ok=True)
            
            # 파일 이동
            final_file_path = final_dir / file_path.name
            
            logger.info(f"📦 파일 이동 중...")
            logger.info(f"  원본: {file_path}")
            logger.info(f"  대상: {final_file_path}")
            
            # 파일 이동 (shutil.move는 원자적 작업)
            shutil.move(str(file_path), str(final_file_path))
            
            # 파일 권한 설정 (선택사항)
            os.chmod(final_file_path, 0o644)
            
            logger.info(f"✅ 파일 이동 완료: {final_file_path}")
            
        except Exception as e:
            logger.error(f"❌ 파일 이동 실패: {file_path.name} - {e}")
        finally:
            self.processing_files.discard(str(file_path))
    
    def _extract_time_based_directory(self, filename: str) -> Optional[str]:
        """파일명에서 시간 정보를 추출하여 YYYY/MM/DD/HH 경로 생성"""
        try:
            # 파일명 패턴: {vessel_name}_stream{number}_{YYMMDD}_{HHMMSS}.mp4
            # 예: vesselTest_stream01_241212_143052.mp4
            
            # 정규식으로 날짜/시간 부분 추출
            pattern = r'_(\d{6})_(\d{6})\.mp4$'
            match = re.search(pattern, filename)
            
            if not match:
                logger.warning(f"파일명 패턴이 맞지 않음: {filename}")
                return None
            
            date_str = match.group(1)  # YYMMDD
            time_str = match.group(2)  # HHMMSS
            
            # 날짜 파싱 (YY -> 20YY로 변환)
            year = 2000 + int(date_str[:2])
            month = int(date_str[2:4])
            day = int(date_str[4:6])
            hour = int(time_str[:2])
            
            # YYYY/MM/DD/HH 형식으로 경로 생성
            time_dir = f"{year:04d}/{month:02d}/{day:02d}/{hour:02d}"
            
            logger.debug(f"시간 기반 경로 생성: {filename} -> {time_dir}")
            return time_dir
            
        except Exception as e:
            logger.error(f"시간 정보 추출 실패: {filename} - {e}")
            return None

class FileMoverService:
    """파일 이동 서비스 메인 클래스"""
    
    def __init__(self):
        self.temp_path = get_env_value('TEMP_OUTPUT_PATH', './output/temp/')
        self.final_path = get_env_value('FINAL_OUTPUT_PATH', '/mnt/raid5')
        self.observer = None
        self.running = False
        
        # 신호 핸들러 등록
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """종료 신호 처리"""
        logger.info(f"종료 신호 수신: {signum}")
        self.stop()
    
    def start(self):
        """파일 모니터링 시작"""
        try:
            logger.info("🚀 RTSP 영상 파일 이동 서비스 시작")
            
            # 임시 경로 존재 확인
            temp_path_obj = Path(self.temp_path)
            if not temp_path_obj.exists():
                logger.info(f"임시 경로 생성: {self.temp_path}")
                temp_path_obj.mkdir(parents=True, exist_ok=True)
            
            # 최종 경로 확인/생성
            final_path_obj = Path(self.final_path)
            try:
                final_path_obj.mkdir(parents=True, exist_ok=True)
                logger.info(f"최종 저장 경로 확인: {self.final_path}")
            except PermissionError:
                logger.warning(f"최종 경로 권한 없음: {self.final_path} (파일 이동 시 생성 시도)")
            
            # 파일 시스템 이벤트 핸들러 설정
            event_handler = VideoFileMoveHandler(self.temp_path, self.final_path)
            
            # Observer 설정 및 시작
            self.observer = Observer()
            self.observer.schedule(event_handler, self.temp_path, recursive=False)
            self.observer.start()
            self.running = True
            
            logger.info("📡 파일 모니터링 활성화됨")
            logger.info("Press Ctrl+C to stop...")
            
            # 메인 루프
            try:
                while self.running:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
                
        except Exception as e:
            logger.error(f"❌ 서비스 시작 실패: {e}")
            return False
        finally:
            self.stop()
        
        return True
    
    def stop(self):
        """파일 모니터링 중지"""
        if self.running:
            logger.info("🛑 파일 이동 서비스 중지 중...")
            self.running = False
            
            if self.observer:
                self.observer.stop()
                self.observer.join()
                logger.info("✅ 파일 모니터링 종료됨")

def main():
    """메인 함수"""
    logger.info("=" * 50)
    logger.info("RTSP 영상 파일 자동 이동 서비스")
    logger.info("=" * 50)
    
    # 환경변수 로드
    try:
        from dotenv import load_dotenv
        load_dotenv()
        logger.info("환경변수 로드 완료")
    except ImportError:
        logger.warning("python-dotenv 패키지가 설치되지 않음. 시스템 환경변수만 사용")
    except Exception as e:
        logger.warning(f"환경변수 로드 실패: {e}")
    
    # 서비스 실행
    service = FileMoverService()
    
    try:
        success = service.start()
        if not success:
            sys.exit(1)
    except Exception as e:
        logger.error(f"예상치 못한 오류: {e}")
        sys.exit(1)
    
    logger.info("서비스가 정상적으로 종료되었습니다.")

if __name__ == "__main__":
    main() 