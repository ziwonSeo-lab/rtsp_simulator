"""
RTSP 시뮬레이터 워커 프로세스 모듈

이 모듈은 multi-process_rtsp.py에서 추출된 워커 프로세스 함수들을 포함합니다:
- rtsp_capture_process: RTSP 캡처 프로세스 (시뮬레이션 지원)
- blur_worker_process: 블러 처리 워커
- save_worker_process: 저장 워커

각 워커 프로세스는 멀티프로세싱 환경에서 독립적으로 실행되며,
큐를 통해 데이터를 주고받습니다.
"""

import cv2
import time
import queue
import logging
import os
import random
import importlib.util
import subprocess
import numpy as np
from datetime import datetime
from typing import Optional
from dataclasses import dataclass


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
        
        # 입력 스트림 설정 - 정확한 15fps로 해석
        cmd.extend([
            '-f', 'rawvideo',
            '-vcodec', 'rawvideo',
            '-s', f'{self.width}x{self.height}',
            '-pix_fmt', 'bgr24',
            '-r', str(self.fps),  # 입력 FPS를 15로 강제 설정
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
            # CRF 모드: compression_level을 직접 사용 (18 = 고화질)
            crf_value = max(0, min(51, self.config.compression_level))
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
        
        # 강력한 15fps 고정 설정
        cmd.extend(['-r', str(self.fps)])  # 출력 FPS 15로 강제 설정
        cmd.extend(['-vsync', 'cfr'])  # Constant Frame Rate로 15fps 강제 유지
        cmd.extend(['-g', str(self.config.keyframe_interval)])
        cmd.extend(['-pix_fmt', self.config.pixel_format])
        
        # 프레임 레이트 추가 강제 설정
        if self.config.video_codec in ['libx264', 'libx265']:
            cmd.extend(['-fflags', '+genpts'])  # PTS 재생성
        
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
            logger = logging.getLogger(__name__)
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
            logger = logging.getLogger(__name__)
            logger.error(f"FFmpeg 프로세스 시작 실패: {e}")
            self.is_opened = False
    
    def write(self, frame: np.ndarray):
        if not self.is_opened or not self.process:
            logger = logging.getLogger(__name__)
            logger.warning(f"FFmpeg writer가 열려있지 않음")
            return False
        
        try:
            if self.process.poll() is not None:
                logger = logging.getLogger(__name__)
                logger.error(f"FFmpeg 프로세스가 종료됨: 종료 코드 {self.process.poll()}")
                self.is_opened = False
                return False
            
            if frame is None or frame.size == 0:
                logger = logging.getLogger(__name__)
                logger.error(f"잘못된 프레임")
                return False
            
            expected_height, expected_width = self.height, self.width
            actual_height, actual_width = frame.shape[:2]
            if actual_height != expected_height or actual_width != expected_width:
                frame = cv2.resize(frame, (expected_width, expected_height))
            
            frame_bytes = frame.tobytes()
            
            if self.process.stdin.closed:
                logger = logging.getLogger(__name__)
                logger.error("FFmpeg stdin이 닫혀있음")
                self.is_opened = False
                return False
            
            self.process.stdin.write(frame_bytes)
            self.process.stdin.flush()
            self.frame_count += 1
            return True
            
        except BrokenPipeError as e:
            logger = logging.getLogger(__name__)
            logger.error(f"FFmpeg 파이프 끊어짐: {e}")
            self.is_opened = False
            return False
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"FFmpeg 프레임 쓰기 실패: {e}")
            return False
    
    def release(self):
        if self.process:
            try:
                self.process.stdin.close()
                self.process.wait(timeout=10)
                logger = logging.getLogger(__name__)
                logger.info(f"FFmpeg 프로세스 종료됨: {self.filepath} ({self.frame_count} 프레임)")
            except subprocess.TimeoutExpired:
                logger = logging.getLogger(__name__)
                logger.warning(f"FFmpeg 프로세스 강제 종료: {self.filepath}")
                self.process.kill()
            except Exception as e:
                logger = logging.getLogger(__name__)
                logger.error(f"FFmpeg 프로세스 종료 오류: {e}")
            finally:
                self.process = None
        
        self.is_opened = False
    
    def isOpened(self):
        return self.is_opened and self.process is not None


def rtsp_capture_process(source, stream_id, thread_id, blur_queue, preview_queue, stats_dict, stop_event, config):
    """RTSP 캡처 프로세스 (시뮬레이션 지원)"""
    logger = logging.getLogger(f"CAPTURE_{stream_id}")
    current_pid = os.getpid()
    logger.info(f"📹 캡처 프로세스 실행 중 - PID: {current_pid}, Stream: {stream_id}, Thread: {thread_id}")
    logger.info(f"   🔗 소스: {source}")
    logger.info(f"   🆔 프로세스 ID: {current_pid}")
    
    # 블러 모듈 로드
    blur_module = None
    if config.blur_module_path:
        try:
            spec = importlib.util.spec_from_file_location(f"blur_module_{stream_id}", config.blur_module_path)
            blur_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(blur_module)
            
            if hasattr(blur_module, 'HeadBlurrer'):
                head_blurrer = blur_module.HeadBlurrer(conf_threshold=0.3, enable_face_counting=False)
                blur_module.apply_blur = lambda frame, should_detect=None: head_blurrer.process_frame(frame, frame_interval=config.blur_interval, should_detect=should_detect)
            
            logger.info(f"Stream {stream_id}: 블러 모듈 로드 성공")
        except Exception as e:
            logger.error(f"Stream {stream_id}: 블러 모듈 로드 실패 - {e}")
            blur_module = None
    
    # OpenCV VideoCapture 초기화
    cap = cv2.VideoCapture(source)
    
    # 안전한 속성 설정
    try:
        if hasattr(cv2, 'CAP_PROP_BUFFER_SIZE'):
            cap.set(cv2.CAP_PROP_BUFFER_SIZE, 1)
    except Exception as e:
        logger.debug(f"CAP_PROP_BUFFER_SIZE 설정 실패 (OpenCV 버전 호환성): {e}")
    
    if config.force_fps:
        try:
            if hasattr(cv2, 'CAP_PROP_FPS'):
                cap.set(cv2.CAP_PROP_FPS, config.input_fps)
        except Exception as e:
            logger.debug(f"CAP_PROP_FPS 설정 실패 (OpenCV 버전 호환성): {e}")
    
    # 연결 설정
    if source.startswith('rtsp://') or source.startswith('http://'):
        try:
            if hasattr(cv2, 'CAP_PROP_OPEN_TIMEOUT_MSEC'):
                cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, config.connection_timeout * 1000)
            if hasattr(cv2, 'CAP_PROP_READ_TIMEOUT_MSEC'):
                cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000)
        except Exception as e:
            logger.debug(f"연결 설정 실패: {e}")
    
    if not cap.isOpened():
        logger.error(f"소스 연결 실패: {source}")
        return
    
    # 첫 번째 프레임 읽기 시도
    ret, frame = cap.read()
    if not ret:
        cap.release()
        logger.error(f"소스에서 프레임 읽기 실패: {source}")
        return
    
    # 실제 FPS 확인
    actual_fps = cap.get(cv2.CAP_PROP_FPS)
    if actual_fps > 0:
        logger.info(f"Stream {stream_id}: 실제 FPS - {actual_fps:.1f}")
    
    logger.info(f"Stream {stream_id}: 소스 연결 성공")
    
    frame_count = 0
    failed_count = 0
    start_time = time.time()
    
    # FPS 측정을 위한 변수들
    fps_frame_count = 0
    fps_start_time = time.time()
    last_fps_report = time.time()
    
    # 정밀한 15fps 제어를 위한 변수들
    TARGET_FPS = config.input_fps
    frame_interval = 1.0 / TARGET_FPS  # 66.67ms for 15fps
    last_capture_time = start_time
    frame_timing_error = 0.0  # 누적 타이밍 오차 보정
    
    # 타이밍 정확성을 위한 고해상도 시계 사용 (time 모듈은 이미 import됨)
    if hasattr(time, 'time_ns'):
        get_time = lambda: time.time_ns() / 1_000_000_000.0  # 나노초 해상도
    else:
        get_time = time.time
    
    # 적응적 FPS 제어 - RTSP 소스가 느릴 때 보상
    adaptive_interval = frame_interval
    fps_adjustment_factor = 1.0
    
    # 버벅임 방지를 위한 프레임 버퍼
    frame_buffer = []
    buffer_size = 3  # 최대 3프레임 버퍼
    
    logger.info(f"Stream {stream_id}: 정밀 FPS 제어 시작 - 목표: {TARGET_FPS}fps, 간격: {frame_interval*1000:.2f}ms, 고해상도 타이밍 활성화")
    
    try:
        while not stop_event.is_set():
            # 최대 처리 시간 체크
            if config.max_duration_seconds:
                elapsed_time = time.time() - start_time
                if elapsed_time >= config.max_duration_seconds:
                    break
            
            # 고해상도 타이밍으로 버벅임 방지
            current_time = get_time()
            expected_time = last_capture_time + frame_interval
            time_error = current_time - expected_time
            
            # 엄격한 타이밍 제어 (버벅임 방지 우선)
            if time_error < -0.002:  # 2ms 이상 빠르면 정확한 대기
                sleep_time = min(-time_error, 0.050)  # 최대 50ms 대기
                time.sleep(sleep_time)
                current_time = get_time()
            elif time_error > frame_interval * 0.3:  # 30% 이상 늦으면 스킵하지 않고 처리
                logger.debug(f"Stream {stream_id}: 타이밍 지연 {time_error*1000:.1f}ms, 계속 진행")
            
            # 다음 프레임 타이밍 계산
            last_capture_time = expected_time  # 누적 오차 방지를 위해 예상 시간 사용
            
            ret, frame = cap.read()
            
            # 프레임 품질 검증 (버벅임 유발 프레임 제거)
            if ret and frame is not None:
                # 기본적인 프레임 유효성 검사
                if frame.size == 0 or frame.shape[0] == 0 or frame.shape[1] == 0:
                    ret = False
                # 완전히 검은색이거나 완전히 흰색인 프레임 제거 (손상 가능성)
                elif np.all(frame == 0) or np.all(frame == 255):
                    logger.debug(f"Stream {stream_id}: 비정상 프레임 건너뜀 (균일색상)")
                    ret = False
            
            if not ret:
                failed_count += 1
                if failed_count > 10:
                    logger.error("연속 프레임 읽기 실패 - 재연결 시도")
                    cap.release()
                    time.sleep(config.reconnect_interval)
                    cap = cv2.VideoCapture(source)
                    
                    # 재연결 시에도 안전한 속성 설정
                    try:
                        if hasattr(cv2, 'CAP_PROP_BUFFER_SIZE'):
                            cap.set(cv2.CAP_PROP_BUFFER_SIZE, 1)
                    except Exception as e:
                        logger.debug(f"재연결 시 CAP_PROP_BUFFER_SIZE 설정 실패: {e}")
                    
                    if config.force_fps:
                        try:
                            if hasattr(cv2, 'CAP_PROP_FPS'):
                                cap.set(cv2.CAP_PROP_FPS, config.input_fps)
                        except Exception as e:
                            logger.debug(f"재연결 시 CAP_PROP_FPS 설정 실패: {e}")
                    
                    failed_count = 0
                continue
            
            failed_count = 0
            
            # 통계 업데이트
            stats_dict[f'{stream_id}_received'] = stats_dict.get(f'{stream_id}_received', 0) + 1
            
            # 프레임 손실 시뮬레이션
            if random.random() < config.frame_loss_rate:
                stats_dict[f'{stream_id}_lost'] = stats_dict.get(f'{stream_id}_lost', 0) + 1
                logger.debug(f"Stream {stream_id}: 프레임 {frame_count} 시뮬레이션 손실")
                continue
            
            # 블러 처리 간격 적용
            should_blur = (frame_count % config.blur_interval == 0)
            
            # 프레임 순서 보장을 위한 엄격한 타이밍 제어
            frame_count += 1
            capture_timestamp = datetime.fromtimestamp(current_time)
            
            # 프레임 중복 방지를 위한 고유 ID 생성
            frame_unique_id = f"{stream_id}_{frame_count}_{int(current_time * 1000000)}"
            
            work_item = {
                'stream_id': stream_id,
                'thread_id': thread_id,
                'frame': frame.copy(),
                'timestamp': capture_timestamp,
                'frame_number': frame_count,
                'frame_unique_id': frame_unique_id,  # 중복 방지용 고유 ID
                'config': config,
                'should_blur': should_blur,
                'capture_time': current_time,
                'target_fps': TARGET_FPS,
                'sequence_number': frame_count  # 순서 보장용 시퀀스 번호
            }
            
            # 강제적 순차 처리로 버벅임 방지
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    # 더 긴 타임아웃으로 순서 보장
                    blur_queue.put(work_item, timeout=0.5)  # 500ms 타임아웃
                    break
                except queue.Full:
                    if attempt < max_retries - 1:
                        # 큐가 가득 찬 경우 잠시 대기 후 재시도
                        time.sleep(0.01 * (attempt + 1))  # 점진적 백오프
                    else:
                        # 최종 시도: 가장 오래된 프레임 제거
                        try:
                            discarded_item = blur_queue.get_nowait()
                            logger.debug(f"Stream {stream_id}: 프레임 {discarded_item.get('frame_number', 'unknown')} 버림 (최종 시도)")
                            blur_queue.put_nowait(work_item)
                        except:
                            logger.warning(f"Stream {stream_id}: 프레임 {frame_count} 완전 건너뜀")
                            continue
            fps_frame_count += 1
            
            # 1초마다 FPS 측정 및 출력
            current_fps_time = time.time()
            if current_fps_time - last_fps_report >= 1.0:
                fps_duration = current_fps_time - fps_start_time
                if fps_duration > 0:
                    capture_fps = fps_frame_count / fps_duration
                    logger.info(f"📹 [CAPTURE] Stream {stream_id}: 실제 캡처 FPS = {capture_fps:.1f}, "
                               f"목표 = {config.input_fps:.1f}, 블러큐: {blur_queue.qsize()}")
                
                # FPS 측정 리셋
                fps_frame_count = 0
                fps_start_time = current_fps_time
                last_fps_report = current_fps_time
                
            # 주기적 로깅 및 메모리 정리
            if frame_count % 500 == 0:
                import gc
                gc.collect()
                logger.info(f"Stream {stream_id}: {frame_count}프레임, 메모리 정리 완료")
            elif frame_count % 100 == 0:
                logger.debug(f"Stream {stream_id}: {frame_count}프레임")
            
            # 미리보기는 블러 처리 후 blur_worker_process에서 처리
                    
    except Exception as e:
        logger.error(f"캡처 프로세스 오류: {e}")
    finally:
        cap.release()
        logger.info(f"캡처 프로세스 종료 - Stream {stream_id}, 총 {frame_count}개 프레임")


def blur_worker_process(worker_id, blur_queue, save_queues, preview_queue, stats_dict, stop_event):
    """블러 처리 워커 - 블러 결과 캐시 기능 포함"""
    logger = logging.getLogger(f"BLUR_WORKER_{worker_id}")
    current_pid = os.getpid()
    logger.info(f"🔍 블러 워커 실행 중 - PID: {current_pid}, Worker: {worker_id}")
    logger.info(f"   🆔 프로세스 ID: {current_pid}")
    logger.info(f"   🔧 워커 ID: {worker_id}")
    logger.info(f"   🎯 스마트 블러 시스템 활성화 - 3프레임마다 위치 탐지, 캐시된 위치에 블러 적용")
    
    processed_count = 0
    
    # 변수 초기화 (안전성 향상)
    frame = None
    processed_frame = None
    work_item = None
    
    # 블러 위치 정보 캐시 (스트림별)
    blur_cache = {}  # {stream_id: {'last_blur_locations': [], 'last_detection_frame': int}}
    
    # FPS 측정을 위한 변수들
    blur_fps_frame_count = 0
    blur_fps_start_time = time.time()
    blur_last_fps_report = time.time()
    
    # blur_module을 각 워커에서 독립적으로 로드 (캐시용)
    blur_modules_cache = {}
    
    try:
        while not stop_event.is_set() or not blur_queue.empty():
            try:
                work_item = blur_queue.get(timeout=1.0)
                
                # work_item 구조 검증
                if not isinstance(work_item, dict):
                    logger.warning(f"Worker {worker_id}: 잘못된 work_item 형식 - {type(work_item)}")
                    time.sleep(0.1)
                    continue
                
                # 필수 키 확인
                required_keys = ['frame', 'config', 'stream_id', 'thread_id']
                missing_keys = [key for key in required_keys if key not in work_item]
                if missing_keys:
                    logger.warning(f"Worker {worker_id}: work_item에 누락된 키 - {missing_keys}")
                    time.sleep(0.1)
                    continue
                
                frame = work_item['frame']
                config = work_item['config']
                stream_id = work_item['stream_id']
                thread_id = work_item['thread_id']
                
                # blur_module을 워커에서 독립적으로 로드 (캐시 활용)
                blur_module = None
                if config.blur_module_path and config.blur_module_path not in blur_modules_cache:
                    try:
                        import importlib.util
                        spec = importlib.util.spec_from_file_location(f"blur_module_worker_{worker_id}", config.blur_module_path)
                        blur_module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(blur_module)
                        
                        if hasattr(blur_module, 'HeadBlurrer'):
                            head_blurrer = blur_module.HeadBlurrer(conf_threshold=0.3, enable_face_counting=False)
                            blur_module.apply_blur = lambda frame, should_detect=None: head_blurrer.process_frame(frame, frame_interval=config.blur_interval, should_detect=should_detect)
                        
                        blur_modules_cache[config.blur_module_path] = blur_module
                        logger.info(f"Worker {worker_id}: 블러 모듈 로드 성공")
                    except Exception as e:
                        logger.warning(f"Worker {worker_id}: 블러 모듈 로드 실패, 기본 블러 사용 - {e}")
                        blur_modules_cache[config.blur_module_path] = None
                elif config.blur_module_path in blur_modules_cache:
                    blur_module = blur_modules_cache[config.blur_module_path]
                
                # 성능 프로파일링 시작
                if not config.high_performance_mode:
                    start_time = time.time()
                
                # 단순한 블러 처리 (모든 프레임 처리 + 간격 제어)
                stream_id = work_item['stream_id']
                frame_number = work_item['frame_number']
                should_blur = work_item.get('should_blur', True)  # 3프레임마다 True
                
                if config.blur_enabled:
                    # 블러 모듈 사용 시도 (fallback 지원)
                    if blur_module and hasattr(blur_module, 'apply_blur'):
                        try:
                            processed_frame = blur_module.apply_blur(frame, should_detect=should_blur)
                            logger.debug(f"Worker {worker_id}: {stream_id} 커스텀 블러 적용 (프레임 {frame_number}, 탐지: {should_blur})")
                        except Exception as e:
                            logger.warning(f"Worker {worker_id}: 커스텀 블러 모듈 오류, 기본 블러 사용 - {e}")
                            processed_frame = cv2.GaussianBlur(frame, (15, 15), 0)
                    else:
                        # 기본 가우시안 블러 (모듈 로드 실패 시)
                        processed_frame = cv2.GaussianBlur(frame, (15, 15), 0)
                        if processed_count == 0:  # 첫 번째만 로그 출력
                            logger.info(f"Worker {worker_id}: 블러 모듈 없음, 기본 가우시안 블러 사용")
                else:
                    processed_frame = frame
                
                # 오버레이 처리
                if config.overlay_enabled and not config.high_performance_mode:
                    frame_number = work_item['frame_number']
                    current_time = work_item['timestamp'].strftime("%Y-%m-%d %H:%M:%S")
                    
                    overlay_lines = [
                        f"Ship: {config.ship_name}, Time: {current_time}, GPS: {config.latitude}, {config.longitude}"
                    ]
                    
                    # 반투명 배경 추가
                    for i, line in enumerate(overlay_lines):
                        y_pos = 25 + i * 25
                        (text_width, text_height), _ = cv2.getTextSize(line, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
                        
                        # 배경 영역이 이미지 범위를 벗어나지 않도록 확인
                        h, w = processed_frame.shape[:2]
                        if y_pos + 8 <= h and 5 + text_width + 10 <= w:
                            try:
                                bg_rect = np.zeros((text_height + 10, text_width + 10, 3), dtype=np.uint8)
                                processed_frame[y_pos-text_height-2:y_pos+8, 5:5+text_width+10] = cv2.addWeighted(
                                    processed_frame[y_pos-text_height-2:y_pos+8, 5:5+text_width+10], 0.5, bg_rect, 0.5, 0
                                )
                            except:
                                pass  # 크기 불일치 시 무시
                        
                        # 텍스트 오버레이
                        cv2.putText(processed_frame, line, (10, y_pos), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 1, cv2.LINE_AA)
                elif config.overlay_enabled:
                    # 고성능 모드에서는 기본 텍스트만
                    text = f"Thread {thread_id} - Processed"
                    cv2.putText(processed_frame, text, (10, 30), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                
                # 스트림별 저장 큐로 전송 (원본 + 블러 영상 지원)
                if config.save_enabled:
                    stream_id = work_item['stream_id']
                    save_item = {
                        'stream_id': stream_id,
                        'thread_id': work_item['thread_id'],
                        'original_frame': frame,  # 원본 프레임 추가
                        'processed_frame': processed_frame,  # 블러 처리된 프레임
                        'timestamp': work_item['timestamp'],
                        'frame_number': work_item['frame_number'],
                        'config': config
                    }
                    
                    try:
                        # 해당 스트림 전용 큐에 전송
                        if stream_id in save_queues:
                            save_queues[stream_id].put_nowait(save_item)
                        else:
                            logger.warning(f"Worker {worker_id}: 스트림 {stream_id}의 저장큐가 없음")
                    except queue.Full:
                        try:
                            if stream_id in save_queues:
                                save_queues[stream_id].get_nowait()
                                save_queues[stream_id].put_nowait(save_item)
                                logger.warning(f"Worker {worker_id}: 스트림 {stream_id} 저장큐 오버플로우")
                        except:
                            pass
                
                # 미리보기 큐로 전송 (블러 처리된 프레임, 3프레임마다)
                if config.preview_enabled and work_item['frame_number'] % 3 == 0:
                    try:
                        h, w = processed_frame.shape[:2]
                        if w > 320:
                            new_w = 320
                            new_h = int(h * 320 / w)
                            preview_frame = cv2.resize(processed_frame, (new_w, new_h))
                        else:
                            preview_frame = processed_frame
                        
                        preview_queue.put_nowait((stream_id, preview_frame.copy(), 
                                                f"Blurred Thread {thread_id}"))
                    except queue.Full:
                        pass  # 미리보기 큐가 가득 찬 경우 무시
                    except Exception as e:
                        logger.debug(f"Worker {worker_id}: 미리보기 큐 전송 실패 - {e}")
                
                # 통계 업데이트
                stats_dict[f'{stream_id}_processed'] = stats_dict.get(f'{stream_id}_processed', 0) + 1
                processed_count += 1
                blur_fps_frame_count += 1
                
                # 1초마다 FPS 측정 및 출력
                current_blur_time = time.time()
                if current_blur_time - blur_last_fps_report >= 1.0:
                    blur_duration = current_blur_time - blur_fps_start_time
                    if blur_duration > 0:
                        blur_fps = blur_fps_frame_count / blur_duration
                        total_save_queue_size = sum(q.qsize() for q in save_queues.values())
                        logger.info(f"🔍 [BLUR] Worker {worker_id}: 블러 처리 FPS = {blur_fps:.1f}, "
                                   f"저장큐 총합: {total_save_queue_size}")
                    
                    # FPS 측정 리셋
                    blur_fps_frame_count = 0
                    blur_fps_start_time = current_blur_time
                    blur_last_fps_report = current_blur_time
                
                # 메모리 정리 (100프레임마다)
                if processed_count % 100 == 0:
                    import gc
                    gc.collect()
                    total_save_queue_size = sum(q.qsize() for q in save_queues.values())
                    logger.info(f"Worker {worker_id}: {processed_count}프레임 처리, 저장큐 총합: {total_save_queue_size}, 메모리 정리 완료")
                elif processed_count % 50 == 0:
                    total_save_queue_size = sum(q.qsize() for q in save_queues.values())
                    logger.info(f"Worker {worker_id}: {processed_count}프레임 처리, 저장큐 총합: {total_save_queue_size}")
                
                # 원본 프레임 메모리 해제 (안전한 방법)
                try:
                    if 'frame' in locals():
                        del frame
                except:
                    pass
                
                try:
                    if 'processed_frame' in locals() and 'frame' in locals() and processed_frame is not frame:
                        del processed_frame
                except:
                    pass
                        
            except queue.Empty:
                time.sleep(0.1)
                continue
            except Exception as e:
                logger.error(f"블러 워커 오류: {e}")
                continue
                
    except Exception as e:
        logger.error(f"블러 워커 오류: {e}")
    finally:
        logger.info(f"블러 워커 종료 - Worker {worker_id}, 처리: {processed_count}")


def save_worker_process(worker_id, save_queue, stats_dict, stop_event, base_output_dir, config, shared_stream_last_save_times, stream_timing_lock, dedicated_stream_id=None):
    """저장 워커 - 스트림별 독립적인 15fps 제어"""
    logger = logging.getLogger(f"SAVE_WORKER_{worker_id}")
    current_pid = os.getpid()
    logger.info(f"💾 저장 워커 실행 중 - PID: {current_pid}, Worker: {worker_id}")
    logger.info(f"   🆔 프로세스 ID: {current_pid}")
    logger.info(f"   🔧 워커 ID: {worker_id}")
    logger.info(f"   📁 저장 경로: {base_output_dir}")
    if dedicated_stream_id:
        logger.info(f"   🎯 전용 스트림: {dedicated_stream_id} (스트림별 독립적 15fps 제어)")
    
    # 설정 유효성 검사
    if not config:
        logger.error(f"Worker {worker_id}: config가 None입니다. 저장 워커를 종료합니다.")
        return
    
    # 2단계 저장 설정
    two_stage_enabled = hasattr(config, 'two_stage_storage') and config.two_stage_storage
    if two_stage_enabled:
        logger.info(f"   🔄 2단계 저장 활성화: SSD({config.ssd_temp_path}) → HDD({config.hdd_final_path})")
        temp_prefix = getattr(config, 'temp_file_prefix', 't_')
        # 2단계 저장일 때는 SSD 경로 사용
        base_output_dir = config.ssd_temp_path
    else:
        temp_prefix = ""
        logger.info(f"   📂 일반 저장 모드")
    
    # 시간 기반 디렉토리 구조 함수
    def get_time_based_directory(timestamp):
        """YYYY/MM/DD/HH 형식의 디렉토리 경로 생성"""
        return os.path.join(
            str(timestamp.year),
            f"{timestamp.month:02d}",
            f"{timestamp.day:02d}",
            f"{timestamp.hour:02d}"
        )
    
    saved_count = 0
    video_writers = {}
    frame_counts = {}
    file_counters = {}
    video_frame_counts = {}
    stream_dirs = {}
    stream_file_start_times = {}  # 각 스트림별 파일 시작 시간 추적
    last_sequence_numbers = {}  # 스트림별 마지막 처리된 시퀀스 번호 (중복 방지)
    processed_frame_ids = set()  # 처리된 프레임 ID 집합 (중복 방지)
    
    # 정밀한 15fps 제어 변수 (워커별 로컬)
    TARGET_FPS = 15.0
    frame_interval = 1.0 / TARGET_FPS  # 66.67ms 간격
    last_save_time = 0  # 로컬 타이밍 제어
    timing_tolerance = frame_interval * 0.3  # 30% 허용 오차 (20ms) - 완화
    accumulated_error = 0.0  # 누적 타이밍 오차
    
    logger.info(f"   ⏱️ FFmpeg CFR 모드로 15fps 제어 - 모든 프레임을 FFmpeg에 전달")
    if dedicated_stream_id:
        logger.info(f"   🎯 {dedicated_stream_id} 전용 워커 - FFmpeg 기반 15fps 제어")
    
    # FPS 측정을 위한 변수들
    save_fps_frame_count = 0
    save_fps_start_time = time.time()
    save_last_fps_report = time.time()
    save_stream_fps = {}  # 스트림별 FPS 측정
    
    def _check_ffmpeg():
        try:
            result = subprocess.run(['ffmpeg', '-version'], 
                                  capture_output=True, text=True, timeout=5)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def _save_single_frame(frame_data, output_dir):
        """단일 프레임 저장 (이미지)"""
        filename = f"frame_{frame_data['timestamp'].strftime('%Y%m%d_%H%M%S_%f')[:-3]}.jpg"
        filepath = os.path.join(output_dir, filename)
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, 85]
        cv2.imwrite(filepath, frame_data['frame'], encode_params)
    
    try:
        while not stop_event.is_set() or not save_queue.empty():
            try:
                save_item = save_queue.get(timeout=1.0)
                
                stream_id = save_item['stream_id']
                
                # 프레임 중복 방지 - 고유 ID 체크
                frame_unique_id = save_item.get('frame_unique_id')
                sequence_number = save_item.get('sequence_number', 0)
                
                if frame_unique_id and frame_unique_id in processed_frame_ids:
                    logger.debug(f"Worker {worker_id}: 중복 프레임 건너뜀 - {frame_unique_id}")
                    continue
                
                # 엄격한 순서 보장 - 버벅임 방지
                last_seq = last_sequence_numbers.get(stream_id, 0)
                if sequence_number > 0:
                    # 순서가 크게 역행하는 프레임은 버벅임 원인이므로 제거
                    if sequence_number < last_seq - 2:  # 2프레임 이전은 건너뜀 (더 엄격)
                        logger.debug(f"Worker {worker_id}: 순서 역행 프레임 제거 - seq:{sequence_number}, last:{last_seq}")
                        continue
                    # 너무 앞서가는 프레임도 제거 (미래 프레임)
                    elif sequence_number > last_seq + 10:  # 10프레임 이상 앞서면 이상
                        logger.debug(f"Worker {worker_id}: 미래 프레임 제거 - seq:{sequence_number}, last:{last_seq}")
                        continue
                
                # 처리된 프레임으로 기록
                if frame_unique_id:
                    processed_frame_ids.add(frame_unique_id)
                    # 메모리 관리: 너무 많은 ID 저장 방지
                    if len(processed_frame_ids) > 1000:
                        processed_frame_ids.clear()
                
                last_sequence_numbers[stream_id] = max(last_sequence_numbers.get(stream_id, 0), sequence_number)
                
                # 원본 프레임과 블러 프레임 추출 (backward compatibility)
                original_frame = save_item.get('original_frame', save_item.get('frame'))
                processed_frame = save_item.get('processed_frame', save_item.get('frame'))
                timestamp = save_item['timestamp']
                config = save_item['config']
                
                # 전용 스트림 워커인 경우 다른 스트림 프레임 무시
                if dedicated_stream_id and stream_id != dedicated_stream_id:
                    continue
                
                # FFmpeg vsync cfr에 15fps 제어를 맡김 - 모든 프레임을 전달
                current_time = time.time()
                
                # 시간 기반 디렉토리 생성 (스트림별 구분 없음)
                time_based_dir = get_time_based_directory(timestamp)
                if stream_id not in stream_dirs:
                    # 시간 기반 디렉토리 사용
                    stream_dir = os.path.join(base_output_dir, time_based_dir)
                    os.makedirs(stream_dir, exist_ok=True)
                    stream_dirs[stream_id] = stream_dir
                    frame_counts[stream_id] = 0
                    file_counters[stream_id] = 0
                    video_frame_counts[stream_id] = 0
                    stream_file_start_times[stream_id] = current_time  # 스트림 시작 시간 기록
                    logger.info(f"Worker {worker_id}: {stream_id} 시간 기반 디렉토리 생성 - {time_based_dir}")
                else:
                    # 시간이 바뀌었는지 확인하고 디렉토리 업데이트
                    current_time_dir = get_time_based_directory(timestamp)
                    if stream_dirs[stream_id] != os.path.join(base_output_dir, current_time_dir):
                        # 시간이 바뀌었으므로 새 디렉토리로 변경
                        new_stream_dir = os.path.join(base_output_dir, current_time_dir)
                        os.makedirs(new_stream_dir, exist_ok=True)
                        stream_dirs[stream_id] = new_stream_dir
                        logger.info(f"Worker {worker_id}: {stream_id} 시간 변경으로 새 디렉토리 - {current_time_dir}")
                
                frame_counts[stream_id] += 1
                
                # 첫 번째 프레임 로그
                if last_save_time == 0:
                    last_save_time = current_time
                    logger.info(f"Worker {worker_id}: {stream_id} 저장 시작 - FFmpeg CFR 모드로 15fps 제어")
                
                # 모든 프레임을 FFmpeg에 전달 (FFmpeg가 15fps로 조정)
                
                # 영상으로만 저장 (container_format이 비디오 포맷인 경우)
                if config.container_format in ['mp4', 'mkv', 'webm', 'avi']:
                    # 시간 기반 새 비디오 파일 시작 조건 체크
                    should_start_new_file = False
                    
                    if stream_id not in video_writers:
                        # 첫 번째 파일
                        should_start_new_file = True
                    elif hasattr(config, 'save_interval_seconds') and config.save_interval_seconds > 0:
                        # 시간 기반 파일 분할 (우선순위)
                        file_start_time = stream_file_start_times.get(stream_id, current_time)
                        file_duration = current_time - file_start_time
                        if file_duration >= config.save_interval_seconds:
                            should_start_new_file = True
                            logger.info(f"Worker {worker_id}: {stream_id} 시간 기반 파일 분할 "
                                       f"({file_duration:.1f}초 ≥ {config.save_interval_seconds}초)")
                    else:
                        # 프레임 기반 파일 분할 (폴백)
                        if video_frame_counts[stream_id] >= config.save_interval:
                            should_start_new_file = True
                            logger.info(f"Worker {worker_id}: {stream_id} 프레임 기반 파일 분할 "
                                       f"({video_frame_counts[stream_id]} ≥ {config.save_interval})")
                    
                    if should_start_new_file:
                        
                        # 기존 비디오 writer 종료 및 2단계 저장 처리
                        if stream_id in video_writers:
                            try:
                                current_filepath = None
                                current_base_filename = None
                                
                                # 현재 파일 정보 저장 (2단계 저장용)
                                if hasattr(video_writers[stream_id], 'filepath'):
                                    current_filepath = video_writers[stream_id].filepath
                                    if two_stage_enabled and temp_prefix in os.path.basename(current_filepath):
                                        current_base_filename = os.path.basename(current_filepath).replace(temp_prefix, "", 1)
                                
                                video_writers[stream_id].release()
                                logger.info(f"Stream {stream_id}: 비디오 저장 완료 - {video_frame_counts[stream_id]}프레임 "
                                          f"(part{file_counters[stream_id]:03d})")
                                
                                # 2단계 저장: 임시 파일명에서 접두사 제거 (파일 모니터가 자동 감지)
                                if two_stage_enabled and current_filepath and current_base_filename:
                                    # 임시 파일에서 접두사 제거
                                    final_temp_filepath = current_filepath.replace(temp_prefix, "", 1)
                                    
                                    try:
                                        # 파일명에서 접두사 제거 (이름 변경) - 모니터가 이 이벤트를 감지함
                                        if os.path.exists(current_filepath):
                                            logger.info(f"Stream {stream_id}: 임시 파일 이름 변경 시작 - {os.path.basename(current_filepath)} → {os.path.basename(final_temp_filepath)}")
                                            os.rename(current_filepath, final_temp_filepath)
                                            logger.info(f"Stream {stream_id}: ✅ 임시 파일 이름 변경 완료 - {os.path.basename(final_temp_filepath)} (모니터가 감지 예정)")
                                            
                                            # 파일명 변경 후 짧은 대기 (inotify 이벤트 처리 시간 확보)
                                            time.sleep(0.1)
                                        else:
                                            logger.warning(f"Stream {stream_id}: 임시 파일을 찾을 수 없음 - {current_filepath}")
                                    
                                    except Exception as rename_error:
                                        logger.error(f"Stream {stream_id}: 임시 파일 이름 변경 실패 - {rename_error}")
                                elif two_stage_enabled:
                                    logger.warning(f"Stream {stream_id}: 2단계 저장 활성화되었지만 파일 정보가 부족함")
                                else:
                                    logger.info(f"Stream {stream_id}: 일반 저장 모드 (2단계 저장 비활성화)")
                        
                            except Exception as e:
                                logger.error(f"Stream {stream_id}: 기존 writer 해제 오류 - {e}")
                            finally:
                                if stream_id in video_writers:
                                    del video_writers[stream_id]
                        
                        # 새 비디오 파일 시작
                        file_counters[stream_id] += 1
                        video_frame_counts[stream_id] = 0
                        stream_file_start_times[stream_id] = current_time  # 파일 시작 시간 기록
                        
                        # 파일명 생성 (원본/블러 비디오 지원)
                        timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S")
                        
                        # 원본 비디오 파일명 (블러 비활성화 시)
                        base_filename = f"{config.ship_name}_{stream_id}_{timestamp_str}.{config.container_format}"
                        
                        if two_stage_enabled:
                            # 임시 파일명 (접두사 추가)
                            filename = f"{temp_prefix}{base_filename}"
                            filepath = os.path.join(stream_dirs[stream_id], filename)
                        else:
                            # 일반 저장
                            filename = base_filename
                            filepath = os.path.join(stream_dirs[stream_id], filename)
                        
                        # 비디오 writer 초기화 (원본/블러 뒤 비디오 지원)
                        height, width = processed_frame.shape[:2]  # processed_frame을 기준으로 크기 결정
                        fps = max(1.0, config.input_fps)
                        
                        logger.info(f"Stream {stream_id}: 비디오 writer 생성 시작")
                        logger.info(f"  파일: {filename}")
                        logger.info(f"  해상도: {width}x{height} @ {fps}fps")
                        logger.info(f"  컨테이너: {config.container_format}")
                        
                        writer_created = False
                        
                        # FFmpeg 시도
                        if _check_ffmpeg():
                            try:
                                logger.info(f"Stream {stream_id}: Enhanced FFmpeg writer 생성 시도")
                                video_writers[stream_id] = EnhancedFFmpegVideoWriter(filepath, fps, width, height, config)
                                
                                if video_writers[stream_id].isOpened():
                                    logger.info(f"Stream {stream_id}: ✅ Enhanced FFmpeg 비디오 시작 성공 - {filename}")
                                    writer_created = True
                                else:
                                    raise Exception("Enhanced FFmpeg writer가 열리지 않음")
                                    
                            except Exception as e:
                                logger.warning(f"Stream {stream_id}: Enhanced FFmpeg writer 생성 실패 - {e}")
                                logger.info(f"Stream {stream_id}: OpenCV VideoWriter로 폴백 시도")
                                if stream_id in video_writers:
                                    try:
                                        video_writers[stream_id].release()
                                    except:
                                        pass
                                    del video_writers[stream_id]
                        
                        # OpenCV VideoWriter 폴백
                        if not writer_created:
                            logger.info(f"Stream {stream_id}: OpenCV VideoWriter 생성 시도")
                            
                            fourcc_options = []
                            
                            if config.container_format == 'mp4':
                                fourcc_options = ['mp4v', 'MJPG', 'XVID']
                            elif config.container_format == 'avi':
                                fourcc_options = ['XVID', 'MJPG', 'mp4v']
                            elif config.container_format == 'mkv':
                                fourcc_options = ['XVID', 'mp4v', 'MJPG']
                            elif config.container_format == 'webm':
                                fourcc_options = ['VP80', 'VP90', 'MJPG']
                            else:
                                fourcc_options = ['MJPG', 'XVID', 'mp4v']
                            
                            for fourcc_str in fourcc_options:
                                try:
                                    logger.info(f"Stream {stream_id}: {fourcc_str} 코덱으로 OpenCV VideoWriter 시도")
                                    
                                    try:
                                        fourcc = cv2.VideoWriter_fourcc(*fourcc_str)
                                    except Exception as fourcc_error:
                                        logger.warning(f"Stream {stream_id}: {fourcc_str} 코덱 지원하지 않음 - {fourcc_error}")
                                        continue
                                    
                                    if fourcc_str in ['MJPG', 'DIVX']:
                                        test_filepath = filepath.replace(f'.{config.container_format}', '.avi')
                                    elif fourcc_str in ['VP80', 'VP90']:
                                        test_filepath = filepath.replace(f'.{config.container_format}', '.webm')
                                    else:
                                        test_filepath = filepath
                                    
                                    writer = None
                                    try:
                                        writer = cv2.VideoWriter(test_filepath, fourcc, fps, (width, height))
                                        
                                        if not writer.isOpened():
                                            logger.warning(f"Stream {stream_id}: {fourcc_str} 코덱으로 VideoWriter 열기 실패")
                                            if writer:
                                                writer.release()
                                            continue
                                        
                                        video_writers[stream_id] = writer
                                        logger.info(f"Stream {stream_id}: ✅ OpenCV 비디오 시작 성공 - {os.path.basename(test_filepath)} ({fourcc_str})")
                                        writer_created = True
                                        break
                                            
                                    except Exception as writer_error:
                                        logger.warning(f"Stream {stream_id}: {fourcc_str} VideoWriter 생성 중 오류 - {writer_error}")
                                        if writer:
                                            try:
                                                writer.release()
                                            except:
                                                pass
                                        continue
                                        
                                except Exception as e:
                                    logger.error(f"Stream {stream_id}: {fourcc_str} 코덱 시도 중 전체 오류 - {e}")
                                    continue
                            
                            if not writer_created:
                                logger.error(f"Stream {stream_id}: 모든 VideoWriter 생성 시도 실패")
                                logger.error(f"Stream {stream_id}: 영상 저장 불가 - 프레임 건너뜀")
                                continue
                        
                        # 최종 확인
                        if stream_id not in video_writers or not video_writers[stream_id].isOpened():
                            logger.error(f"Stream {stream_id}: 비디오 writer 생성 최종 실패")
                            if stream_id in video_writers:
                                del video_writers[stream_id]
                            continue
                    
                    # 블러 처리된 프레임을 비디오에 추가
                    if stream_id in video_writers and video_writers[stream_id].isOpened():
                        try:
                            # 블러 활성화 여부에 따라 원본 또는 블러 처리된 프레임 저장
                            frame_to_save = original_frame if not config.blur_enabled else processed_frame
                            success = video_writers[stream_id].write(frame_to_save)
                            if success:
                                video_frame_counts[stream_id] += 1
                                saved_count += 1
                                save_fps_frame_count += 1
                                stats_dict[f'{stream_id}_saved'] = stats_dict.get(f'{stream_id}_saved', 0) + 1
                                
                                # 스트림별 FPS 카운터 초기화
                                if stream_id not in save_stream_fps:
                                    save_stream_fps[stream_id] = {'count': 0, 'start_time': current_time}
                                save_stream_fps[stream_id]['count'] += 1
                                
                                # 1초마다 FPS 측정 및 출력
                                if current_time - save_last_fps_report >= 1.0:
                                    save_duration = current_time - save_fps_start_time
                                    if save_duration > 0:
                                        actual_save_fps = save_fps_frame_count / save_duration
                                        
                                        if dedicated_stream_id:
                                            logger.info(f"💾 [SAVE] Worker {worker_id} ({dedicated_stream_id}): "
                                                       f"저장 FPS = {actual_save_fps:.1f}, 목표 = {TARGET_FPS:.1f}, "
                                                       f"큐: {save_queue.qsize()}")
                                        else:
                                            # 스트림별 FPS 계산 (레거시)
                                            stream_fps_info = []
                                            for sid, fps_data in save_stream_fps.items():
                                                stream_duration = current_time - fps_data['start_time']
                                                if stream_duration > 0:
                                                    stream_fps = fps_data['count'] / stream_duration
                                                    stream_fps_info.append(f"{sid}:{stream_fps:.1f}")
                                            
                                            logger.info(f"💾 [SAVE] Worker {worker_id}: 전체 저장 FPS = {actual_save_fps:.1f}, "
                                                       f"스트림별 FPS = [{', '.join(stream_fps_info)}], 큐: {save_queue.qsize()}")
                                    
                                    # FPS 측정 리셋
                                    save_fps_frame_count = 0
                                    save_fps_start_time = current_time
                                    save_last_fps_report = current_time
                                    # 스트림별 FPS 카운터 리셋
                                    for sid in save_stream_fps:
                                        save_stream_fps[sid] = {'count': 0, 'start_time': current_time}
                            else:
                                logger.error(f"Stream {stream_id}: 비디오 프레임 쓰기 실패")
                                
                                # Writer 상태 확인 및 복구
                                writer = video_writers[stream_id]
                                
                                if hasattr(writer, 'process') and writer.process:
                                    poll_status = writer.process.poll()
                                    logger.error(f"Stream {stream_id}: FFmpeg 프로세스 상태 - poll={poll_status}")
                                    if poll_status is not None:
                                        logger.error(f"Stream {stream_id}: FFmpeg 프로세스 종료됨, writer 재생성 예정")
                                else:
                                    logger.error(f"Stream {stream_id}: OpenCV VideoWriter 쓰기 실패, writer 재생성 예정")
                                
                                # Writer 정리 후 다음 프레임에서 재생성
                                try:
                                    writer.release()
                                except Exception as release_error:
                                    logger.error(f"Stream {stream_id}: Writer 해제 오류 - {release_error}")
                                
                                del video_writers[stream_id]
                                video_frame_counts[stream_id] = config.save_interval
                                
                        except Exception as write_error:
                            logger.error(f"Stream {stream_id}: 프레임 쓰기 중 예외 발생 - {write_error}")
                            if stream_id in video_writers:
                                try:
                                    video_writers[stream_id].release()
                                except:
                                    pass
                                del video_writers[stream_id]
                else:
                    # 이미지 저장 (비디오 포맷이 아닌 경우)
                    logger.warning(f"Stream {stream_id}: 지원하지 않는 포맷 '{config.container_format}', 이미지로 저장")
                    _save_single_frame({
                        'frame': frame,
                        'timestamp': timestamp
                    }, stream_dirs[stream_id])
                    saved_count += 1
                    stats_dict[f'{stream_id}_saved'] = stats_dict.get(f'{stream_id}_saved', 0) + 1
                        
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"저장 워커 오류: {e}")
                continue
                
    except Exception as e:
        logger.error(f"저장 워커 오류: {e}")
    finally:
        # 모든 비디오 writer 정리 및 2단계 저장 처리
        for stream_id, writer in video_writers.items():
            try:
                current_filepath = None
                current_base_filename = None
                
                # 현재 파일 정보 저장 (2단계 저장용)
                if hasattr(writer, 'filepath'):
                    current_filepath = writer.filepath
                    if two_stage_enabled and temp_prefix in os.path.basename(current_filepath):
                        current_base_filename = os.path.basename(current_filepath).replace(temp_prefix, "", 1)
                
                writer.release()
                logger.info(f"Stream {stream_id}: 최종 비디오 저장 완료 - {video_frame_counts.get(stream_id, 0)}프레임")
                
                # 2단계 저장: 종료 시에도 남은 파일 처리 (파일 모니터가 자동 감지)
                if two_stage_enabled and current_filepath and current_base_filename:
                    final_temp_filepath = current_filepath.replace(temp_prefix, "", 1)
                    
                    try:
                        if os.path.exists(current_filepath):
                            os.rename(current_filepath, final_temp_filepath)
                            logger.info(f"Stream {stream_id}: 종료 시 임시 파일 이름 변경 완료 - {os.path.basename(final_temp_filepath)} (모니터가 감지 예정)")
                            
                            # 파일명 변경 후 짧은 대기 (inotify 이벤트 처리 시간 확보)
                            time.sleep(0.1)
                    
                    except Exception as rename_error:
                        logger.error(f"Stream {stream_id}: 종료 시 임시 파일 이름 변경 실패 - {rename_error}")
                
            except Exception as cleanup_error:
                logger.error(f"Stream {stream_id}: 최종 정리 중 오류 - {cleanup_error}")
                
        logger.info(f"저장 워커 종료 - Worker {worker_id}, 저장: {saved_count}")


def file_move_worker_process(worker_id, file_move_queue, stats_dict, stop_event, ssd_path, hdd_path, temp_prefix):
    """파일 이동 워커 (SSD → HDD)"""
    logger = logging.getLogger(f"FILE_MOVE_WORKER_{worker_id}")
    current_pid = os.getpid()
    logger.info(f"🚛 파일 이동 워커 실행 중 - PID: {current_pid}, Worker: {worker_id}")
    logger.info(f"   🆔 프로세스 ID: {current_pid}")
    logger.info(f"   🔧 워커 ID: {worker_id}")
    logger.info(f"   📂 SSD 경로: {ssd_path}")
    logger.info(f"   📁 HDD 경로: {hdd_path}")
    logger.info(f"   🔄 2단계 저장 파일 이동 시작")
    
    moved_count = 0
    
    # 시간 기반 디렉토리 구조 함수
    def get_time_based_directory_from_filename(filename):
        """파일명에서 시간 정보를 추출하여 YYYY/MM/DD/HH 형식의 디렉토리 경로 생성"""
        try:
            # 파일명 형식: shipname_streamid_YYYYMMDD_HHMMSS.ext
            logger.debug(f"Worker {worker_id}: 파일명 파싱 시작 - {filename}")
            
            # 확장자 제거
            name_without_ext = os.path.splitext(filename)[0]
            parts = name_without_ext.split('_')
            
            logger.debug(f"Worker {worker_id}: 파일명 파트 - {parts}")
            
            if len(parts) >= 4:  # shipname, streamid, YYYYMMDD, HHMMSS
                # YYYYMMDD 부분 찾기 (4번째 파트)
                date_str = None
                for part in parts:
                    if isinstance(part, str) and len(part) == 8 and part.isdigit():
                        date_str = part
                        logger.debug(f"Worker {worker_id}: 날짜 문자열 찾음 - {date_str}")
                        break
                if not date_str:
                    logger.warning(f"Worker {worker_id}: 날짜 문자열을 찾을 수 없음 - {parts}")
                    return None
                
                # HHMMSS 부분 찾기 (4번째 파트)
                time_str = None
                for part in parts:
                    if isinstance(part, str) and len(part) == 6 and part.isdigit():
                        time_str = part
                        logger.debug(f"Worker {worker_id}: 시간 문자열 찾음 - {time_str}")
                        break
                else:
                    logger.warning(f"Worker {worker_id}: 시간 문자열을 찾을 수 없음 - {parts}")
                    return None
                
                # 시간 정보 파싱
                year = int(date_str[:4])
                month = int(date_str[4:6])
                day = int(date_str[6:8])
                hour = int(time_str[:2])
                
                time_dir = os.path.join(
                    str(year),
                    f"{month:02d}",
                    f"{day:02d}",
                    f"{hour:02d}"
                )
                
                logger.info(f"Worker {worker_id}: 시간 기반 디렉토리 생성 성공 - {time_dir}")
                return time_dir
            else:
                logger.warning(f"Worker {worker_id}: 파일명 파트가 부족함 - {parts}")
                return None
                
        except Exception as e:
            logger.error(f"Worker {worker_id}: 파일명에서 시간 정보 추출 실패 - {filename}: {e}")
            return None
    
    try:
        # HDD 최종 저장 경로 생성
        os.makedirs(hdd_path, exist_ok=True)
        
        while not stop_event.is_set() or not file_move_queue.empty():
            try:
                move_item = file_move_queue.get(timeout=1.0)
                logger.info(f"Worker {worker_id}: 파일 이동 작업 수신 - {move_item}")
                
                if not isinstance(move_item, dict):
                    logger.warning(f"Worker {worker_id}: 잘못된 move_item 형식 - {type(move_item)}")
                    continue
                
                # move_item 구조: {'temp_filepath': str, 'final_filename': str, 'stream_id': str}
                temp_filepath = move_item['temp_filepath']
                final_filename = move_item['final_filename']
                stream_id = move_item['stream_id']
                
                logger.info(f"Worker {worker_id}: 파일 이동 시작 - {final_filename} (스트림: {stream_id})")
                
                # 임시 파일이 존재하는지 확인
                if not os.path.exists(temp_filepath):
                    logger.warning(f"Worker {worker_id}: 임시 파일이 존재하지 않음 - {temp_filepath}")
                    continue
                
                # HDD 시간 기반 디렉토리 생성 (스트림별 구분 없음)
                time_based_dir = get_time_based_directory_from_filename(final_filename)
                if time_based_dir:
                    hdd_time_dir = os.path.join(hdd_path, time_based_dir)
                    os.makedirs(hdd_time_dir, exist_ok=True)
                    
                    # 최종 파일 경로
                    final_filepath = os.path.join(hdd_time_dir, final_filename)
                    logger.debug(f"Worker {worker_id}: 시간 기반 디렉토리 사용 - {time_based_dir}")
                else:
                    # 시간 정보 추출 실패 시 기본 경로 사용
                    hdd_default_dir = os.path.join(hdd_path, "unknown_time")
                    os.makedirs(hdd_default_dir, exist_ok=True)
                    final_filepath = os.path.join(hdd_default_dir, final_filename)
                    logger.warning(f"Worker {worker_id}: 시간 정보 추출 실패, 기본 디렉토리 사용 - {final_filename}")
                
                # 파일 이동 시도
                try:
                    import shutil
                    logger.info(f"Worker {worker_id}: 파일 이동 시작 - {temp_filepath} → {final_filepath}")
                    
                    # 파일 크기 확인
                    if os.path.exists(temp_filepath):
                        file_size = os.path.getsize(temp_filepath)
                        logger.info(f"Worker {worker_id}: 이동할 파일 크기 - {file_size} bytes")
                    
                    shutil.move(temp_filepath, final_filepath)
                    moved_count += 1
                    
                    # 통계 업데이트
                    stats_dict[f'{stream_id}_moved'] = stats_dict.get(f'{stream_id}_moved', 0) + 1
                    
                    logger.info(f"Worker {worker_id}: ✅ 파일 이동 완료 - {final_filename}")
                    
                    if moved_count % 10 == 0:
                        logger.info(f"Worker {worker_id}: {moved_count}개 파일 이동 완료, 큐: {file_move_queue.qsize()}")
                    
                except Exception as move_error:
                    logger.error(f"Worker {worker_id}: ❌ 파일 이동 실패 - {temp_filepath} → {final_filepath}")
                    logger.error(f"Worker {worker_id}: 이동 오류: {move_error}")
                    
                    # 이동 실패 시 임시 파일 정리
                    try:
                        if os.path.exists(temp_filepath):
                            os.remove(temp_filepath)
                            logger.warning(f"Worker {worker_id}: 이동 실패한 임시 파일 정리됨 - {temp_filepath}")
                    except Exception as cleanup_error:
                        logger.error(f"Worker {worker_id}: 임시 파일 정리 실패 - {cleanup_error}")
                        
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"파일 이동 워커 오류: {e}")
                continue
                
    except Exception as e:
        logger.error(f"파일 이동 워커 오류: {e}")
    finally:
        logger.info(f"파일 이동 워커 종료 - Worker {worker_id}, 이동: {moved_count}")


def file_monitor_worker_process(file_move_queue, stats_dict, stop_event, ssd_path, temp_prefix):
    """파일 시스템 모니터 워커 (inotify 기반)"""
    logger = logging.getLogger("FILE_MONITOR_WORKER")
    current_pid = os.getpid()
    logger.info(f"👁️ 파일 모니터 워커 실행 중 - PID: {current_pid}")
    logger.info(f"   🆔 프로세스 ID: {current_pid}")
    logger.info(f"   📂 모니터링 경로: {ssd_path}")
    logger.info(f"   🏷️ 임시 파일 접두사: {temp_prefix}")
    logger.info(f"   🔄 2단계 저장 모니터링 시작")
    logger.info(f"   📊 file_move_queue 존재: {file_move_queue is not None}")
    logger.info(f"   🛑 stop_event 상태: {stop_event.is_set()}")
    
    detected_count = 0
    
    try:
        # inotify 사용 가능 확인
        try:
            import inotify_simple
            from inotify_simple import INotify, flags
            logger.info("✅ inotify_simple 모듈 사용")
        except ImportError:
            # watchdog 라이브러리 사용 (fallback)
            try:
                from watchdog.observers import Observer
                from watchdog.events import FileSystemEventHandler
                logger.info("✅ watchdog 모듈 사용 (fallback)")
                use_watchdog = True
            except ImportError:
                logger.error("❌ inotify_simple과 watchdog 모듈을 모두 찾을 수 없습니다.")
                logger.error("다음 명령으로 설치하세요: pip install inotify_simple 또는 pip install watchdog")
                return
        else:
            use_watchdog = False
        
        # SSD 경로 생성
        os.makedirs(ssd_path, exist_ok=True)
        
        if use_watchdog:
            # watchdog 기반 모니터링
            class FileEventHandler(FileSystemEventHandler):
                def __init__(self, monitor_worker):
                    self.monitor_worker = monitor_worker
                
                def on_moved(self, event):
                    # 파일 이름 변경 이벤트 (t_ 접두사 제거)
                    if not event.is_directory:
                        logger.info(f"👁️ watchdog MOVED 이벤트 감지: {event.dest_path}")
                        self.monitor_worker.handle_file_event(event.dest_path, "MOVED_TO")
                
                def on_created(self, event):
                    # 새 파일 생성 이벤트
                    if not event.is_directory:
                        logger.info(f"👁️ watchdog CREATED 이벤트 감지: {event.src_path}")
                        self.monitor_worker.handle_file_event(event.src_path, "CREATE")
            
            # 모니터 워커 클래스
            class WatchdogMonitor:
                def __init__(self):
                    self.detected_count = 0
                
                def handle_file_event(self, filepath, event_type):
                    nonlocal detected_count, file_move_queue, stats_dict, logger, temp_prefix
                    
                    try:
                        filename = os.path.basename(filepath)
                        logger.info(f"👁️ 파일 이벤트 처리 시작: {filename} (타입: {event_type})")
                        
                        # 비디오 파일인지 확인 (temp_prefix 제거 후 감지)
                        if filename.lower().endswith(('.mp4', '.mkv', '.avi', '.webm')):
                            logger.info(f"👁️ 비디오 파일 감지: {filename}")
                            
                            # 스트림 ID 추출
                            try:
                                name_without_ext = os.path.splitext(filename)[0]
                                parts = name_without_ext.split('_')
                                logger.info(f"👁️ 파일명 파트 분석: {parts}")
                                
                                if len(parts) >= 2:
                                    stream_id = parts[1]
                                    if not stream_id.startswith('stream'):
                                        logger.debug(f"👁️ 스트림 ID가 아님: {stream_id}")
                                        return
                                    logger.info(f"👁️ 스트림 ID 추출 성공: {stream_id}")
                                else:
                                    logger.warning(f"👁️ 파일명 파트 부족: {parts}")
                                    return
                            except Exception as e:
                                logger.error(f"👁️ 스트림 ID 추출 실패: {e}")
                                return
                            
                            # 파일이 실제로 존재하고 접근 가능한지 확인
                            if os.path.exists(filepath) and os.access(filepath, os.R_OK):
                                file_size = os.path.getsize(filepath)
                                logger.info(f"👁️ 파일 존재 확인: {filename} (크기: {file_size} bytes)")
                                
                                # 약간의 대기 (파일 쓰기 완료 확인)
                                time.sleep(0.5)
                                
                                if os.path.exists(filepath):
                                    move_item = {
                                        'temp_filepath': filepath,
                                        'final_filename': filename,
                                        'stream_id': stream_id
                                    }
                                    
                                    try:
                                        file_move_queue.put_nowait(move_item)
                                        detected_count += 1
                                        logger.info(f"📁 파일 감지됨: {filename} (총 {detected_count}개)")
                                        
                                        if detected_count % 10 == 0:
                                            logger.info(f"👁️ 모니터: {detected_count}개 파일 감지, 이동큐: {file_move_queue.qsize()}")
                                        
                                    except queue.Full:
                                        logger.warning(f"👁️ 파일 이동 큐가 가득참 - {filename}")
                                        try:
                                            file_move_queue.get_nowait()
                                            file_move_queue.put_nowait(move_item)
                                        except:
                                            pass
                                else:
                                    logger.warning(f"👁️ 파일이 사라짐: {filename}")
                            else:
                                logger.warning(f"👁️ 파일 접근 불가: {filename}")
                        else:
                            logger.debug(f"👁️ 비디오 파일이 아님: {filename}")
                    
                    except Exception as e:
                        logger.error(f"👁️ 파일 이벤트 처리 오류: {e}")
            
            # watchdog 모니터링 시작
            monitor = WatchdogMonitor()
            event_handler = FileEventHandler(monitor)
            observer = Observer()
            observer.schedule(event_handler, ssd_path, recursive=True)
            observer.start()
            
            logger.info("👁️ watchdog 파일 모니터링 시작됨")
            
            try:
                while not stop_event.is_set():
                    time.sleep(1)
            finally:
                observer.stop()
                observer.join()
        
        else:
            # inotify 기반 모니터링
            inotify = INotify()
            
            # 모든 하위 디렉토리 감시 추가
            watch_descriptors = {}
            
            def add_watch_recursive(path):
                try:
                    wd = inotify.add_watch(path, flags.MOVED_FROM | flags.MOVED_TO | flags.CREATE | flags.CLOSE_WRITE)
                    watch_descriptors[wd] = path
                    logger.info(f"👁️ 감시 추가: {path}")
                    
                    # 하위 디렉토리도 재귀적으로 추가
                    for item in os.listdir(path):
                        item_path = os.path.join(path, item)
                        if os.path.isdir(item_path):
                            add_watch_recursive(item_path)
                except Exception as e:
                    logger.warning(f"👁️ 감시 추가 실패: {path} - {e}")
            
            add_watch_recursive(ssd_path)
            
            # 파일명 변경 추적을 위한 임시 저장소
            moved_from_files = {}  # {cookie: (old_name, old_path)}
            
            logger.info("👁️ inotify 파일 모니터링 시작됨")
            
            while not stop_event.is_set():
                try:
                    # 1초 타임아웃으로 이벤트 읽기
                    events = inotify.read(timeout=1000)
                    
                    # 이벤트가 있을 때만 로그 출력 (스팸 방지)
                    if events:
                        logger.info(f"👁️ 이벤트 읽기 결과: {len(events)}개 이벤트")
                    
                    for event in events:
                        try:
                            # 디버깅: 모든 이벤트 로그
                            event_type = []
                            if event.mask & flags.MOVED_FROM:
                                event_type.append("MOVED_FROM")
                            if event.mask & flags.MOVED_TO:
                                event_type.append("MOVED_TO")
                            if event.mask & flags.CREATE:
                                event_type.append("CREATE")
                            if event.mask & flags.CLOSE_WRITE:
                                event_type.append("CLOSE_WRITE")
                            
                            logger.debug(f"👁️ 이벤트 감지: {event.name} - {', '.join(event_type)} (cookie: {event.cookie})")
                            
                            # 파일 이벤트만 처리
                            if not event.name:
                                continue
                            
                            filepath = os.path.join(watch_descriptors.get(event.wd, ssd_path), event.name)
                            filename = event.name
                            
                            # MOVED_FROM 이벤트 처리 (파일명 변경 시작)
                            if event.mask & flags.MOVED_FROM:
                                moved_from_files[event.cookie] = (filename, filepath)
                                logger.debug(f"👁️ MOVED_FROM 저장: {filename} (cookie: {event.cookie})")
                                continue
                            
                            # MOVED_TO 이벤트 처리 (파일명 변경 완료)
                            if event.mask & flags.MOVED_TO:
                                if event.cookie in moved_from_files:
                                    old_filename, old_filepath = moved_from_files[event.cookie]
                                    logger.info(f"👁️ 파일명 변경 감지: {old_filename} → {filename}")
                                    
                                    # temp_prefix가 제거된 파일인지 확인
                                    if not filename.startswith(temp_prefix) and old_filename.startswith(temp_prefix):
                                        logger.info(f"👁️ 임시 파일명 변경 감지: {old_filename} → {filename}")
                                        
                                        # 스트림 ID 추출
                                        try:
                                            name_without_ext = os.path.splitext(filename)[0]
                                            parts = name_without_ext.split('_')
                                            if len(parts) >= 2:
                                                stream_id = parts[1]
                                                if not stream_id.startswith('stream'):
                                                    logger.debug(f"👁️ 스트림 ID가 아님: {stream_id}")
                                                    del moved_from_files[event.cookie]
                                                    continue
                                                logger.info(f"👁️ 스트림 ID 추출 성공: {stream_id}")
                                            else:
                                                logger.warning(f"👁️ 파일명 파트 부족: {parts}")
                                                del moved_from_files[event.cookie]
                                                continue
                                        except Exception as e:
                                            logger.error(f"👁️ 스트림 ID 추출 실패: {e}")
                                            del moved_from_files[event.cookie]
                                            continue
                                        
                                        # 파일이 실제로 존재하고 접근 가능한지 확인
                                        if os.path.exists(filepath) and os.access(filepath, os.R_OK):
                                            # 약간의 대기 (파일 쓰기 완료 확인)
                                            time.sleep(0.2)
                                            
                                            if os.path.exists(filepath):
                                                move_item = {
                                                    'temp_filepath': filepath,
                                                    'final_filename': filename,
                                                    'stream_id': stream_id
                                                }
                                                
                                                try:
                                                    file_move_queue.put_nowait(move_item)
                                                    detected_count += 1
                                                    logger.info(f"📁 파일 감지됨: {filename} (총 {detected_count}개)")
                                                    
                                                    if detected_count % 10 == 0:
                                                        logger.info(f"👁️ 모니터: {detected_count}개 파일 감지, 이동큐: {file_move_queue.qsize()}")
                                                    
                                                except queue.Full:
                                                    logger.warning(f"👁️ 파일 이동 큐가 가득참 - {filename}")
                                                    try:
                                                        file_move_queue.get_nowait()
                                                        file_move_queue.put_nowait(move_item)
                                                    except:
                                                        pass
                                        
                                        # 처리 완료된 cookie 제거
                                        del moved_from_files[event.cookie]
                                    else:
                                        logger.debug(f"👁️ 일반 파일명 변경 (임시 파일 아님): {old_filename} → {filename}")
                                        del moved_from_files[event.cookie]
                                else:
                                    logger.warning(f"👁️ MOVED_TO 이벤트에 대응하는 MOVED_FROM을 찾을 수 없음 (cookie: {event.cookie})")
                                continue
                            
                            # CREATE 또는 CLOSE_WRITE 이벤트 처리 (새 파일 생성)
                            if event.mask & (flags.CREATE | flags.CLOSE_WRITE):
                                # 비디오 파일인지 확인
                                if filename.lower().endswith(('.mp4', '.mkv', '.avi', '.webm')):
                                    logger.debug(f"👁️ 비디오 파일 감지: {filename}")
                                    
                                    # temp_prefix가 있는 파일은 무시 (아직 임시 파일)
                                    if filename.startswith(temp_prefix):
                                        logger.debug(f"👁️ 임시 파일 무시: {filename}")
                                        continue
                                    
                                    # 스트림 ID 추출
                                    try:
                                        name_without_ext = os.path.splitext(filename)[0]
                                        parts = name_without_ext.split('_')
                                        if len(parts) >= 2:
                                            stream_id = parts[1]
                                            if not stream_id.startswith('stream'):
                                                logger.debug(f"👁️ 스트림 ID가 아님: {stream_id}")
                                                continue
                                            logger.debug(f"👁️ 스트림 ID 추출 성공: {stream_id}")
                                        else:
                                            logger.debug(f"👁️ 파일명 파트 부족: {parts}")
                                            continue
                                    except Exception as e:
                                        logger.debug(f"👁️ 스트림 ID 추출 실패: {e}")
                                        continue
                                    
                                    # 파일이 실제로 존재하고 접근 가능한지 확인
                                    if os.path.exists(filepath) and os.access(filepath, os.R_OK):
                                        # 약간의 대기 (파일 쓰기 완료 확인)
                                        time.sleep(0.1)
                                        
                                        if os.path.exists(filepath):
                                            move_item = {
                                                'temp_filepath': filepath,
                                                'final_filename': filename,
                                                'stream_id': stream_id
                                            }
                                            
                                            try:
                                                file_move_queue.put_nowait(move_item)
                                                detected_count += 1
                                                logger.info(f"📁 파일 감지됨: {filename} (총 {detected_count}개)")
                                                
                                                if detected_count % 10 == 0:
                                                    logger.info(f"👁️ 모니터: {detected_count}개 파일 감지, 이동큐: {file_move_queue.qsize()}")
                                                
                                            except queue.Full:
                                                logger.warning(f"👁️ 파일 이동 큐가 가득참 - {filename}")
                                                try:
                                                    file_move_queue.get_nowait()
                                                    file_move_queue.put_nowait(move_item)
                                                except:
                                                    pass
                        
                        except Exception as e:
                            logger.error(f"👁️ 이벤트 처리 오류: {e}")
                
                except Exception as e:
                    if "timeout" not in str(e).lower():
                        logger.error(f"👁️ inotify 읽기 오류: {e}")
                    continue
            
            # 정리
            for wd in watch_descriptors:
                try:
                    inotify.rm_watch(wd)
                except:
                    pass
            inotify.close()
                
    except Exception as e:
        logger.error(f"파일 모니터 워커 오류: {e}")
    finally:
        logger.info(f"파일 모니터 워커 종료 - 감지: {detected_count}")