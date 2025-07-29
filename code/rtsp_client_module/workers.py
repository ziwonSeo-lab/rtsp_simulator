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
                head_blurrer = blur_module.HeadBlurrer()  # num_camera 매개변수 제거
                blur_module.apply_blur = lambda frame: head_blurrer.process_frame(frame)
            
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
    
    # FPS 제어를 위한 프레임 간격 계산
    frame_interval = 1.0 / config.input_fps
    
    try:
        while not stop_event.is_set():
            # 최대 처리 시간 체크
            if config.max_duration_seconds:
                elapsed_time = time.time() - start_time
                if elapsed_time >= config.max_duration_seconds:
                    break
            
            # FPS 제어
            next_frame_time = start_time + (frame_count + 1) * frame_interval
            sleep_time = next_frame_time - time.time()
            if sleep_time > 0:
                time.sleep(sleep_time)
            
            ret, frame = cap.read()
            
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
            
            # 블러 처리 작업 데이터 준비 (메모리 효율적)
            work_item = {
                'stream_id': stream_id,
                'thread_id': thread_id,
                'frame': frame.copy(),  # 필요한 경우에만 복사
                'timestamp': datetime.now(),
                'frame_number': frame_count,
                'blur_module': blur_module,
                'config': config,
                'should_blur': should_blur  # 블러 처리 여부 플래그 추가
            }
            
            # 블러 큐에 전송 (간격에 따라)
            if should_blur:
                try:
                    blur_queue.put_nowait(work_item)
                except queue.Full:
                    try:
                        blur_queue.get_nowait()
                        blur_queue.put_nowait(work_item)
                        logger.warning(f"Stream {stream_id}: 블러큐 오버플로우")
                    except:
                        pass
                    time.sleep(0.01)  # 큐가 가득 찰 때 CPU 사용률 감소를 위한 대기
            
            frame_count += 1
                
            # 주기적 로깅 및 메모리 정리
            if frame_count % 500 == 0:
                import gc
                gc.collect()
                logger.info(f"Stream {stream_id}: {frame_count}프레임, 블러큐: {blur_queue.qsize()}, 메모리 정리 완료")
            elif frame_count % 100 == 0:
                logger.info(f"Stream {stream_id}: {frame_count}프레임, 블러큐: {blur_queue.qsize()}")
            
            # 미리보기는 블러 처리 후 blur_worker_process에서 처리
                    
    except Exception as e:
        logger.error(f"캡처 프로세스 오류: {e}")
    finally:
        cap.release()
        logger.info(f"캡처 프로세스 종료 - Stream {stream_id}, 총 {frame_count}개 프레임")


def blur_worker_process(worker_id, blur_queue, save_queue, preview_queue, stats_dict, stop_event):
    """블러 처리 워커"""
    logger = logging.getLogger(f"BLUR_WORKER_{worker_id}")
    current_pid = os.getpid()
    logger.info(f"🔍 블러 워커 실행 중 - PID: {current_pid}, Worker: {worker_id}")
    logger.info(f"   🆔 프로세스 ID: {current_pid}")
    logger.info(f"   🔧 워커 ID: {worker_id}")
    
    processed_count = 0
    
    # 변수 초기화 (안전성 향상)
    frame = None
    processed_frame = None
    work_item = None
    
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
                blur_module = work_item.get('blur_module')  # 선택적 키
                stream_id = work_item['stream_id']
                thread_id = work_item['thread_id']
                
                # 성능 프로파일링 시작
                if not config.high_performance_mode:
                    start_time = time.time()
                
                # 블러 처리 (간격에 따라)
                should_blur = work_item.get('should_blur', True)  # 기본값은 True
                
                if config.blur_enabled and should_blur:
                    if blur_module and hasattr(blur_module, 'apply_blur'):
                        try:
                            processed_frame = blur_module.apply_blur(frame)
                        except Exception as e:
                            logger.error(f"Worker {worker_id}: 사용자 블러 처리 오류 - {e}")
                            processed_frame = cv2.GaussianBlur(frame, (15, 15), 0)
                    else:
                        processed_frame = cv2.GaussianBlur(frame, (15, 15), 0)
                else:
                    processed_frame = frame
                
                # 오버레이 처리
                if config.overlay_enabled and not config.high_performance_mode:
                    frame_number = work_item['frame_number']
                    current_time = work_item['timestamp'].strftime("%Y-%m-%d %H:%M:%S")
                    
                    overlay_lines = [
                        f"Frame: {frame_number:06d}",
                        f"Time: {current_time}",
                        f"GPS: {config.latitude:.4f}, {config.longitude:.4f}",
                        f"Thread: {thread_id}"
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
                
                # 저장 큐로 전송
                if config.save_enabled:
                    save_item = {
                        'stream_id': work_item['stream_id'],
                        'thread_id': work_item['thread_id'],
                        'frame': processed_frame,
                        'timestamp': work_item['timestamp'],
                        'frame_number': work_item['frame_number'],
                        'config': config
                    }
                    
                    try:
                        save_queue.put_nowait(save_item)
                    except queue.Full:
                        try:
                            save_queue.get_nowait()
                            save_queue.put_nowait(save_item)
                            logger.warning(f"Worker {worker_id}: 저장큐 오버플로우")
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
                
                # 메모리 정리 (100프레임마다)
                if processed_count % 100 == 0:
                    import gc
                    gc.collect()
                    logger.info(f"Worker {worker_id}: {processed_count}프레임 처리, 저장큐: {save_queue.qsize()}, 메모리 정리 완료")
                elif processed_count % 50 == 0:
                    logger.info(f"Worker {worker_id}: {processed_count}프레임 처리, 저장큐: {save_queue.qsize()}")
                
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


def save_worker_process(worker_id, save_queue, stats_dict, stop_event, base_output_dir):
    """저장 워커"""
    logger = logging.getLogger(f"SAVE_WORKER_{worker_id}")
    current_pid = os.getpid()
    logger.info(f"💾 저장 워커 실행 중 - PID: {current_pid}, Worker: {worker_id}")
    logger.info(f"   🆔 프로세스 ID: {current_pid}")
    logger.info(f"   🔧 워커 ID: {worker_id}")
    logger.info(f"   📁 저장 경로: {base_output_dir}")
    
    saved_count = 0
    video_writers = {}
    frame_counts = {}
    file_counters = {}
    video_frame_counts = {}
    stream_dirs = {}
    
    # 15fps 제한을 위한 타이머 (스트림별)
    last_save_time = {}  # 각 스트림별 마지막 저장 시간
    target_fps = 15.0
    frame_interval = 1.0 / target_fps  # 66.7ms 간격
    
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
                frame = save_item['frame']
                timestamp = save_item['timestamp']
                config = save_item['config']
                
                # 스트림별 디렉토리 생성
                if stream_id not in stream_dirs:
                    stream_dir = os.path.join(base_output_dir, stream_id)
                    os.makedirs(stream_dir, exist_ok=True)
                    stream_dirs[stream_id] = stream_dir
                    frame_counts[stream_id] = 0
                    file_counters[stream_id] = 0
                    video_frame_counts[stream_id] = 0
                    last_save_time[stream_id] = 0  # 첫 프레임은 바로 저장
                
                frame_counts[stream_id] += 1
                
                # 15fps 제한 체크 (66.7ms 간격)
                current_time = time.time()
                time_since_last_save = current_time - last_save_time[stream_id]
                
                if time_since_last_save < frame_interval:
                    # 아직 15fps 간격이 지나지 않았으므로 프레임 스킵
                    continue
                
                # 15fps 간격이 지났으므로 저장 진행
                last_save_time[stream_id] = current_time
                
                # 영상으로만 저장 (container_format이 비디오 포맷인 경우)
                if config.container_format in ['mp4', 'mkv', 'webm', 'avi']:
                    # 새 비디오 파일 시작 조건
                    if (stream_id not in video_writers or 
                        video_frame_counts[stream_id] >= config.save_interval):
                        
                        # 기존 비디오 writer 종료
                        if stream_id in video_writers:
                            try:
                                video_writers[stream_id].release()
                                logger.info(f"Stream {stream_id}: 비디오 저장 완료 - {video_frame_counts[stream_id]}프레임 "
                                          f"(part{file_counters[stream_id]:03d})")
                            except Exception as e:
                                logger.error(f"Stream {stream_id}: 기존 writer 해제 오류 - {e}")
                            finally:
                                if stream_id in video_writers:
                                    del video_writers[stream_id]
                        
                        # 새 비디오 파일 시작
                        file_counters[stream_id] += 1
                        video_frame_counts[stream_id] = 0
                        
                        # 파일명 생성
                        timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S")
                        filename = f"{stream_id}_{timestamp_str}_part{file_counters[stream_id]:03d}.{config.container_format}"
                        filepath = os.path.join(stream_dirs[stream_id], filename)
                        
                        # 비디오 writer 초기화
                        height, width = frame.shape[:2]
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
                    
                    # 프레임을 비디오에 추가
                    if stream_id in video_writers and video_writers[stream_id].isOpened():
                        try:
                            success = video_writers[stream_id].write(frame)
                            if success:
                                video_frame_counts[stream_id] += 1
                                saved_count += 1
                                stats_dict[f'{stream_id}_saved'] = stats_dict.get(f'{stream_id}_saved', 0) + 1
                                
                                if saved_count % 25 == 0:
                                    logger.info(f"Worker {worker_id}: {saved_count}프레임 저장, 큐: {save_queue.qsize()}")
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
        # 모든 비디오 writer 정리
        for stream_id, writer in video_writers.items():
            try:
                writer.release()
                logger.info(f"Stream {stream_id}: 최종 비디오 저장 완료 - {video_frame_counts[stream_id]}프레임")
            except:
                pass
        logger.info(f"저장 워커 종료 - Worker {worker_id}, 저장: {saved_count}")