"""
RTSP 스트림 수신 스레드

단일 RTSP 스트림을 수신하여 프레임 큐에 전달하는 전용 스레드
- 15fps 제어
- 자동 재연결
- 수신 통계 수집
"""

import cv2
import threading
import time
import queue
import logging
import numpy as np
import os
from dataclasses import dataclass
from typing import Optional

from .config import RTSPConfig

logger = logging.getLogger(__name__)

@dataclass
class FrameStats:
	"""프레임 수신 통계"""
	received_frames: int = 0
	lost_frames: int = 0
	error_frames: int = 0
	connection_attempts: int = 0
	last_frame_time: float = 0
	
	def to_dict(self) -> dict:
		"""딕셔너리로 변환"""
		return {
			'received_frames': self.received_frames,
			'lost_frames': self.lost_frames,
			'error_frames': self.error_frames,
			'connection_attempts': self.connection_attempts,
			'last_frame_time': self.last_frame_time,
			'loss_rate': self.lost_frames / max(self.received_frames + self.lost_frames, 1) * 100
		}

class StreamReceiver(threading.Thread):
	"""RTSP 스트림 수신 전용 스레드"""
	
	def __init__(self, config: RTSPConfig, frame_queue: queue.Queue):
		super().__init__(daemon=True)
		self.config = config
		self.frame_queue = frame_queue
		self.running = False
		self.cap = None
		self.stats = FrameStats()
		self.connected = False
		self.blackbox_manager = None
		
		# FPS 제어를 위한 변수
		self.frame_interval = 1.0 / config.input_fps  # 15fps = 0.0667초 간격
		self.last_frame_time = 0
		
		logger.info(f"StreamReceiver 초기화: {config.rtsp_url}")
	
	def set_blackbox_manager(self, blackbox_manager):
		"""블랙박스 매니저 설정"""
		self.blackbox_manager = blackbox_manager
		logger.info("StreamReceiver에 블랙박스 매니저 설정됨")
	
	def run(self):
		"""스트림 수신 메인 루프"""
		logger.info("RTSP 스트림 수신 시작")
		self.running = True
		
		consecutive_failures = 0
		max_failures = 10
		
		while self.running:
			try:
				# RTSP 연결
				if self.cap is None or not self.cap.isOpened():
					if not self.connect_to_stream():
						consecutive_failures += 1
						if consecutive_failures >= max_failures:
							logger.error(f"연속 연결 실패 {max_failures}회, 재연결 대기")
							time.sleep(self.config.reconnect_interval * 2)
							consecutive_failures = 0
						continue
					consecutive_failures = 0
				
				# FPS 제어를 위한 대기
				current_time = time.time()
				if current_time - self.last_frame_time < self.frame_interval:
					sleep_time = self.frame_interval - (current_time - self.last_frame_time)
					time.sleep(sleep_time)
				
				# 프레임 읽기
				ret, frame = self.cap.read()
				
				if not ret:
					logger.warning("프레임 읽기 실패, 재연결 시도")
					self.stats.lost_frames += 1
					self._disconnect()
					time.sleep(self.config.reconnect_interval)
					continue
				
				# 프레임 크기 조정 (필요시)
				frame = self._resize_frame(frame)
				
				# 속도 임계 초과 시 큐 투입을 스킵 (수신 유지, 저장/블러 차단 경량화)
				if self.blackbox_manager and not self.blackbox_manager.is_recording_enabled():
					self.stats.last_frame_time = time.time()
					self.last_frame_time = self.stats.last_frame_time
					continue
				
				# 큐에 프레임 추가 (논블로킹)
				try:
					self.frame_queue.put_nowait((frame, time.time()))
					self.stats.received_frames += 1
					self.stats.last_frame_time = time.time()
					self.last_frame_time = time.time()
					
				except queue.Full:
					# 큐가 가득 찬 경우 프레임 버림
					self.stats.lost_frames += 1
					logger.debug("프레임 큐 가득참, 프레임 버림")
				
			except Exception as e:
				logger.error(f"스트림 수신 오류: {e}")
				self.stats.error_frames += 1
				self._disconnect()
				time.sleep(self.config.reconnect_interval)
		
		# 정리
		self._disconnect()
		logger.info("RTSP 스트림 수신 종료")
	
	def connect_to_stream(self) -> bool:
		"""RTSP 스트림 연결"""
		try:
			logger.info(f"RTSP 연결 시도: {self.config.rtsp_url}")
			self.stats.connection_attempts += 1
			
			# OpenCV VideoCapture 생성 (옵션: GStreamer 사용)
			use_gst = os.getenv('RTSP_USE_GSTREAMER', 'false').lower() in ('1','true','yes','on')
			if use_gst:
				pipeline = self._build_gst_pipeline(self.config.rtsp_url)
				logger.info("GStreamer 파이프라인 사용")
				self.cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
			else:
				self.cap = cv2.VideoCapture(self.config.rtsp_url)
			
			# 연결 설정 최적화 (일부 백엔드에서만 적용)
			try:
				self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # 버퍼 크기 최소화
				self.cap.set(cv2.CAP_PROP_FPS, self.config.input_fps)  # FPS 설정
			except Exception:
				pass
			
			# 타임아웃 설정 (가능한 경우)
			try:
				self.cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, self.config.connection_timeout * 1000)
				self.cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000)
			except:
				pass  # 일부 OpenCV 버전에서 지원하지 않을 수 있음
			
			# 연결 확인
			if not self.cap.isOpened():
				logger.error("RTSP 연결 실패")
				return False
			
			# 첫 번째 프레임 읽기 테스트
			ret, frame = self.cap.read()
			if not ret:
				logger.error("첫 번째 프레임 읽기 실패")
				self.cap.release()
				self.cap = None
				return False
			
			# 연결 성공
			self.connected = True
			actual_fps = self.cap.get(cv2.CAP_PROP_FPS)
			frame_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
			frame_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
			
			logger.info(f"RTSP 연결 성공: {frame_width}x{frame_height} @ {actual_fps:.1f}fps")
			return True
			
		except Exception as e:
			logger.error(f"RTSP 연결 중 오류: {e}")
			self._disconnect()
			return False
	
	def _resize_frame(self, frame: np.ndarray) -> np.ndarray:
		"""프레임 크기 조정 (필요시)"""
		if frame is None:
			return frame
		
		current_height, current_width = frame.shape[:2]
		target_width, target_height = self.config.target_resolution
		
		# 크기가 다른 경우에만 리사이즈
		if current_width != target_width or current_height != target_height:
			frame = cv2.resize(frame, (target_width, target_height))
			logger.debug(f"프레임 크기 조정: {current_width}x{current_height} -> {target_width}x{target_height}")
		
		return frame
	
	def _disconnect(self):
		"""연결 해제"""
		if self.cap:
			self.cap.release()
			self.cap = None
		self.connected = False
	
	def stop(self):
		"""스트림 수신 중지"""
		logger.info("스트림 수신 중지 요청")
		self.running = False
	
	def is_connected(self) -> bool:
		"""연결 상태 확인"""
		return self.connected and self.cap is not None and self.cap.isOpened()
	
	def get_stats(self) -> dict:
		"""수신 통계 반환"""
		stats = self.stats.to_dict()
		stats['connected'] = self.is_connected()
		stats['queue_size'] = self.frame_queue.qsize()
		return stats
	
	def get_stream_info(self) -> dict:
		"""스트림 정보 반환"""
		if not self.is_connected():
			return {}
		
		try:
			return {
				'width': int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
				'height': int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
				'fps': self.cap.get(cv2.CAP_PROP_FPS),
				'fourcc': int(self.cap.get(cv2.CAP_PROP_FOURCC)),
				'frame_count': int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
			}
		except Exception as e:
			logger.error(f"스트림 정보 조회 오류: {e}")
			return {} 

	def _build_gst_pipeline(self, rtsp_url: str) -> str:
		"""Jetson 최적화를 위한 GStreamer 파이프라인 생성"""
		latency = int(os.getenv('RTSP_LATENCY_MS', '200'))
		protocols = os.getenv('RTSP_PROTOCOLS', 'tcp')
		drop = os.getenv('RTSP_DROP', 'true').lower() in ('1','true','yes','on')
		sync = os.getenv('RTSP_SYNC', 'false').lower() in ('1','true','yes','on')
		target_w, target_h = self.config.target_resolution
		# nvv4l2decoder + nvvidconv로 하드웨어 디코드/리사이즈, appsink로 BGR 프레임 수신
		drop_str = 'true' if drop else 'false'
		sync_str = 'true' if sync else 'false'
		pipeline = (
			f"rtspsrc location={rtsp_url} latency={latency} protocols={protocols} ! "
			f"rtph264depay ! h264parse ! nvv4l2decoder ! nvvidconv ! "
			f"video/x-raw, width={target_w}, height={target_h}, format=BGRx ! "
			f"videoconvert ! video/x-raw, format=BGR ! appsink drop={drop_str} max-buffers=1 sync={sync_str}"
		)
		return pipeline 