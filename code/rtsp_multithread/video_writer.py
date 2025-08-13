"""
영상 저장 관리 모듈

FFmpeg 기반 MP4 저장 및 임시 파일 처리
- temp_ 접두사로 저장 중 표시
- 저장 완료 시 정식 파일명으로 변경
- {배이름}_{스트림번호}_{YYMMDD}_{HHMMSS}.mp4 형식
"""

import os
import time
import logging
import subprocess
import numpy as np
import cv2
from datetime import datetime
from typing import Optional
from threading import Thread

try:
    from .config import RTSPConfig, OverlayConfig, generate_filename
except ImportError:
    from config import RTSPConfig, OverlayConfig, generate_filename

logger = logging.getLogger(__name__)

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
    
    def _start_ffmpeg(self):
        """FFmpeg 프로세스 시작"""
        try:
            # FFmpeg 명령어 생성
            input_settings = {
                'width': self.width,
                'height': self.height,
                'fps': self.fps
            }
            cmd = self.config.ffmpeg_config.get_ffmpeg_command(input_settings, self.filepath)
            
            logger.info(f"FFmpeg 명령어: {' '.join(cmd)}")
            
            # FFmpeg 표준출력/표준에러가 파이프를 가득 채워 블로킹되는 것을 방지
            # stdout은 버리고(stderr는 파일로 기록) stdin은 라인버퍼링으로 유지
            log_dir = self.config.temp_output_path if hasattr(self.config, 'temp_output_path') else '.'
            os.makedirs(log_dir, exist_ok=True)
            stderr_path = os.path.join(log_dir, 'ffmpeg_writer.stderr.log')
            self._stderr_file = open(stderr_path, 'ab', buffering=0)

            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=self._stderr_file,
                bufsize=1
            )
            
            # 프로세스가 제대로 시작되었는지 확인 (즉시 실패만 감지)
            if self.process.poll() is not None:
                # 프로세스가 이미 종료됨
                try:
                    logger.error(f"FFmpeg 프로세스 즉시 종료: 코드 {self.process.poll()}")
                except:
                    pass
                self.is_opened = False
                return
            
            self.is_opened = True
            logger.info(f"FFmpeg 프로세스 시작됨: {self.filepath}")
            logger.info(f"비디오 설정: {self.width}x{self.height} @ {self.fps}fps")
            
        except Exception as e:
            logger.error(f"FFmpeg 프로세스 시작 실패: {e}")
            self.is_opened = False
    
    def write(self, frame: np.ndarray):
        """프레임 쓰기"""
        if not self.is_opened or not self.process:
            logger.warning("FFmpeg writer가 열려있지 않음")
            return False
        
        try:
            # FFmpeg 프로세스 상태 확인
            if self.process.poll() is not None:
                logger.error(f"FFmpeg 프로세스가 종료됨: 종료 코드 {self.process.poll()}")
                self.is_opened = False
                return False
            
            # 프레임 크기 검증
            if frame is None or frame.size == 0:
                logger.error("잘못된 프레임")
                return False
            
            # 예상되는 프레임 크기와 비교
            actual_height, actual_width = frame.shape[:2]
            if actual_height != self.height or actual_width != self.width:
                logger.warning(f"프레임 크기 불일치: 예상 {self.width}x{self.height}, 실제 {actual_width}x{actual_height}")
                # 크기 조정
                frame = cv2.resize(frame, (self.width, self.height))
            
            # 프레임을 바이트로 변환
            frame_bytes = frame.tobytes()
            
            # stdin이 열려있는지 확인
            if self.process.stdin.closed:
                logger.error("FFmpeg stdin이 닫혀있음")
                self.is_opened = False
                return False
            
            self.process.stdin.write(frame_bytes)
            self.frame_count += 1
            return True
            
        except BrokenPipeError as e:
            logger.error(f"FFmpeg 파이프 끊어짐: {e}")
            self.is_opened = False
            return False
        except Exception as e:
            logger.error(f"FFmpeg 프레임 쓰기 실패: {e}")
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
                try:
                    if hasattr(self, '_stderr_file') and self._stderr_file:
                        self._stderr_file.close()
                except Exception:
                    pass
        
        self.is_opened = False
    
    def isOpened(self):
        """열림 상태 확인"""
        return self.is_opened and self.process is not None

class VideoWriterManager:
    """영상 저장 관리자 (임시 파일 처리 포함)"""
    
    def __init__(self, config: RTSPConfig):
        self.config = config
        self.current_writer = None
        self.current_temp_file = None   # 현재 임시 파일 경로
        self.current_final_file = None  # 최종 파일 경로
        self.frame_count = 0
        self.video_start_time = None
        # 환경변수에서 비디오 저장 간격 설정 (기본값: 5분)
        self.max_duration = int(os.getenv('VIDEO_SEGMENT_DURATION', 60 * 5))
        
        # 출력 경로 확인
        os.makedirs(config.temp_output_path, exist_ok=True)
        
        # 비동기 finalize 스레드 보관
        self.finalize_threads = []
    
    def start_new_video(self):
        """새 영상 파일 시작 (선오픈/비동기 롤오버)"""
        timestamp = datetime.now()
        
        # 파일명 생성: {배이름}_{스트림번호}_{YYMMDD}_{HHMMSS}.mp4
        filename = generate_filename(self.config.overlay_config, timestamp)
        
        # 임시 파일명: temp_{원본파일명}
        temp_filename = f"temp_{filename}"
        
        new_temp_file = os.path.join(self.config.temp_output_path, temp_filename)
        new_final_file = os.path.join(self.config.temp_output_path, filename)
        
        logger.info(f"새 영상 파일 준비: {temp_filename}")
        
        try:
            # FFmpeg Writer 선오픈
            width, height = self.config.target_resolution
            fps = self.config.input_fps
            
            new_writer = EnhancedFFmpegVideoWriter(
                new_temp_file, fps, width, height, self.config
            )
            
            if not new_writer.isOpened():
                logger.error("새 FFmpeg writer 초기화 실패")
                return False
            
            # 이전 writer 비동기 finalize 준비
            if self.current_writer:
                old_writer = self.current_writer
                old_temp = self.current_temp_file
                old_final = self.current_final_file
                old_start_time = self.video_start_time
                old_frame_count = self.frame_count
                
                self._finalize_previous_writer_async(
                    old_writer, old_temp, old_final, old_start_time, old_frame_count
                )
            
            # 새 writer로 전환
            self.current_writer = new_writer
            self.current_temp_file = new_temp_file
            self.current_final_file = new_final_file
            self.frame_count = 0
            self.video_start_time = time.time()
            
            logger.info(f"영상 저장 시작: {temp_filename}")
            return True
            
        except Exception as e:
            logger.error(f"영상 파일 시작 실패: {e}")
            return False
    
    def write_frame(self, frame: np.ndarray) -> bool:
        """프레임 저장"""
        # writer 없거나 닫혀 있거나 최대 시간 초과 시 새 파일 시작
        if (not self.current_writer or 
            not self.current_writer.isOpened() or 
            (self.video_start_time and time.time() - self.video_start_time >= self.max_duration)):
            if not self.start_new_video():
                return False
        
        # 프레임 저장
        if self.current_writer and self.current_writer.isOpened():
            success = self.current_writer.write(frame)
            if success:
                self.frame_count += 1
                # 100프레임마다 로그 출력
                if self.frame_count % 100 == 0:
                    elapsed = time.time() - self.video_start_time if self.video_start_time else 0
                    logger.info(f"프레임 저장 중: {self.frame_count}프레임 ({elapsed:.1f}초)")
                return True
            else:
                # 첫 프레임(혹은 현재 프레임) 쓰기 실패 시 즉시 재오픈 후 1회 재시도
                logger.warning("프레임 저장 실패 - writer 재오픈 후 재시도")
                if not self.start_new_video():
                    return False
                if self.current_writer and self.current_writer.isOpened():
                    retry = self.current_writer.write(frame)
                    if retry:
                        self.frame_count += 1
                        if self.frame_count % 100 == 0:
                            elapsed = time.time() - self.video_start_time if self.video_start_time else 0
                            logger.info(f"프레임 저장 중: {self.frame_count}프레임 ({elapsed:.1f}초)")
                        return True
                logger.error("프레임 저장 실패 - 재시도도 실패")
                return False
        
        return False
    
    def _finalize_previous_writer_async(self, writer: EnhancedFFmpegVideoWriter, temp_path: str, final_path: str, start_time: Optional[float], frame_count: int):
        """이전 writer를 비동기로 종료하고 파일을 rename"""
        def worker():
            try:
                if writer:
                    writer.release()
                if temp_path and os.path.exists(temp_path):
                    os.rename(temp_path, final_path)
                    file_size = os.path.getsize(final_path) / (1024 * 1024) if os.path.exists(final_path) else 0
                    elapsed = time.time() - start_time if start_time else 0
                    logger.info(f"영상 저장 완료: {os.path.basename(final_path)}")
                    logger.info(f"  프레임 수: {frame_count}")
                    logger.info(f"  영상 길이: {elapsed:.1f}초")
                    logger.info(f"  파일 크기: {file_size:.1f}MB")
                else:
                    logger.error(f"임시 파일이 존재하지 않음(비동기): {temp_path}")
            except Exception as e:
                logger.error(f"영상 파일 비동기 완료 처리 오류: {e}")
        
        t = Thread(target=worker, daemon=True)
        t.start()
        self.finalize_threads.append(t)
    
    def finalize_current_video(self):
        """현재 영상 파일 완료 처리"""
        if not self.current_writer:
            return
        
        try:
            # FFmpeg writer 종료
            self.current_writer.release()
            
            # 임시 파일을 최종 파일명으로 변경
            if os.path.exists(self.current_temp_file):
                os.rename(self.current_temp_file, self.current_final_file)
                
                # 파일 크기 확인
                file_size = os.path.getsize(self.current_final_file) / (1024 * 1024)  # MB
                elapsed = time.time() - self.video_start_time if self.video_start_time else 0
                
                logger.info(f"영상 저장 완료: {os.path.basename(self.current_final_file)}")
                logger.info(f"  프레임 수: {self.frame_count}")
                logger.info(f"  영상 길이: {elapsed:.1f}초")
                logger.info(f"  파일 크기: {file_size:.1f}MB")
            else:
                logger.error(f"임시 파일이 존재하지 않음: {self.current_temp_file}")
                
        except Exception as e:
            logger.error(f"영상 파일 완료 처리 오류: {e}")
            # 임시 파일 정리 시도
            try:
                if os.path.exists(self.current_temp_file):
                    os.remove(self.current_temp_file)
                    logger.info("손상된 임시 파일 삭제됨")
            except:
                pass
        finally:
            self.current_writer = None
            self.current_temp_file = None
            self.current_final_file = None
            self.frame_count = 0
            self.video_start_time = None
    
    def cleanup(self):
        """리소스 정리"""
        logger.info("비디오 라이터 정리 시작")
        
        # 현재 영상 완료
        self.finalize_current_video()
        
        # 비동기 finalize 스레드 대기
        try:
            for t in list(self.finalize_threads):
                t.join(timeout=10)
                if t.is_alive():
                    logger.warning("비동기 finalize 스레드가 시간 내 종료되지 않음")
        except Exception as e:
            logger.warning(f"비동기 finalize 대기 중 오류: {e}")
        
        # 남은 임시 파일들 정리
        try:
            for filename in os.listdir(self.config.temp_output_path):
                if filename.startswith('temp_') and filename.endswith('.mp4'):
                    temp_path = os.path.join(self.config.temp_output_path, filename)
                    try:
                        os.remove(temp_path)
                        logger.info(f"임시 파일 정리: {filename}")
                    except Exception as e:
                        logger.warning(f"임시 파일 정리 실패: {filename} - {e}")
        except Exception as e:
            logger.error(f"임시 파일 정리 중 오류: {e}")
        
        logger.info("비디오 라이터 정리 완료")
    
    def get_status(self) -> dict:
        """현재 저장 상태 반환"""
        if not self.current_writer:
            return {
                'active': False,
                'temp_file': None,
                'final_file': None,
                'frame_count': 0,
                'duration': 0
            }
        
        duration = time.time() - self.video_start_time if self.video_start_time else 0
        
        return {
            'active': True,
            'temp_file': os.path.basename(self.current_temp_file) if self.current_temp_file else None,
            'final_file': os.path.basename(self.current_final_file) if self.current_final_file else None,
            'frame_count': self.frame_count,
            'duration': duration,
            'max_duration': self.max_duration
        } 