"""RTSP 클라이언트 비디오 라이터 모듈"""

import cv2
import numpy as np
import subprocess
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class EnhancedFFmpegVideoWriter:
    """확장된 FFmpeg 기반 비디오 라이터"""
    
    def __init__(self, filepath: str, fps: float, width: int, height: int, config):
        self.filepath = filepath
        self.fps = fps
        self.width = width
        self.height = height
        self.config = config
        self.process = None
        self.is_opened = False
        self.frame_count = 0
        
        if not self._check_ffmpeg():
            raise RuntimeError("FFmpeg가 설치되지 않았습니다.")
        
        self._start_ffmpeg()
    
    def _check_ffmpeg(self):
        try:
            result = subprocess.run(['ffmpeg', '-version'], 
                                  capture_output=True, text=True, timeout=5)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def _get_ffmpeg_command(self):
        cmd = ['ffmpeg', '-y']
        
        if self.config.hardware_acceleration != "none":
            if self.config.hardware_acceleration == "nvidia":
                cmd.extend(['-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda'])
            elif self.config.hardware_acceleration == "intel":
                cmd.extend(['-hwaccel', 'qsv'])
            elif self.config.hardware_acceleration == "amd":
                cmd.extend(['-hwaccel', 'amf'])
        
        cmd.extend([
            '-f', 'rawvideo',
            '-vcodec', 'rawvideo',
            '-s', f'{self.width}x{self.height}',
            '-pix_fmt', 'bgr24',
            '-r', str(self.fps),
            '-i', '-'
        ])
        
        cmd.extend(['-c:v', self.config.video_codec])
        
        if self.config.hardware_acceleration == "nvidia":
            codec_map = {
                'libx264': 'h264_nvenc',
                'libx265': 'hevc_nvenc'
            }
            if self.config.video_codec in codec_map:
                cmd[-1] = codec_map[self.config.video_codec]
        
        if self.config.quality_mode == "crf":
            crf_value = max(0, min(51, 23 - (self.config.compression_level - 5) * 3))
            cmd.extend(['-crf', str(crf_value)])
        elif self.config.quality_mode == "cbr":
            cmd.extend(['-b:v', self.config.bitrate])
        elif self.config.quality_mode == "vbr":
            cmd.extend(['-b:v', self.config.bitrate])
            cmd.extend(['-maxrate', self.config.max_bitrate])
            cmd.extend(['-bufsize', self.config.buffer_size])
        
        if self.config.video_codec in ['libx264', 'libx265']:
            cmd.extend(['-preset', self.config.ffmpeg_preset])
        
        if self.config.ffmpeg_tune != "none" and self.config.video_codec in ['libx264', 'libx265']:
            cmd.extend(['-tune', self.config.ffmpeg_tune])
        
        if self.config.ffmpeg_profile != "none":
            cmd.extend(['-profile:v', self.config.ffmpeg_profile])
        
        if self.config.ffmpeg_level != "none":
            cmd.extend(['-level', self.config.ffmpeg_level])
        
        cmd.extend(['-g', str(self.config.keyframe_interval)])
        cmd.extend(['-pix_fmt', self.config.pixel_format])
        
        if self.config.video_codec == 'libx264':
            cmd.extend(['-x264-params', f'threads=auto:sliced-threads=1:aq-mode=2:me=hex:subme={self.config.compression_level}'])
        elif self.config.video_codec == 'libx265':
            cmd.extend(['-x265-params', f'pools=auto:frame-threads=auto:wpp=1:pmode=1:pme=1:rd={self.config.compression_level}'])
        elif self.config.video_codec == 'libvpx-vp9':
            cmd.extend(['-cpu-used', str(9 - self.config.compression_level)])
            cmd.extend(['-row-mt', '1'])
        
        if self.config.container_format == 'mp4':
            cmd.extend(['-movflags', '+faststart'])
        elif self.config.container_format == 'mkv':
            cmd.extend(['-avoid_negative_ts', 'make_zero'])
        
        if self.config.extra_options:
            extra_opts = self.config.extra_options.split()
            cmd.extend(extra_opts)
        
        cmd.append(self.filepath)
        return cmd
    
    def _start_ffmpeg(self):
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
            
            time.sleep(0.1)
            
            if self.process.poll() is not None:
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
            
        except Exception as e:
            logger.error(f"FFmpeg 프로세스 시작 실패: {e}")
            self.is_opened = False
    
    def write(self, frame: np.ndarray):
        if not self.is_opened or not self.process:
            logger.warning(f"FFmpeg writer가 열려있지 않음")
            return False
        
        try:
            if self.process.poll() is not None:
                logger.error(f"FFmpeg 프로세스가 종료됨: 종료 코드 {self.process.poll()}")
                self.is_opened = False
                return False
            
            if frame is None or frame.size == 0:
                logger.error(f"잘못된 프레임")
                return False
            
            expected_height, expected_width = self.height, self.width
            actual_height, actual_width = frame.shape[:2]
            if actual_height != expected_height or actual_width != expected_width:
                frame = cv2.resize(frame, (expected_width, expected_height))
            
            frame_bytes = frame.tobytes()
            
            if self.process.stdin.closed:
                logger.error("FFmpeg stdin이 닫혀있음")
                self.is_opened = False
                return False
            
            self.process.stdin.write(frame_bytes)
            self.process.stdin.flush()
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
        return self.is_opened and self.process is not None