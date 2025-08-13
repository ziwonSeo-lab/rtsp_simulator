"""
프레임 처리 및 저장 스레드

큐에서 프레임을 읽어 YOLO 블러 처리 및 MP4 저장을 담당하는 전용 스레드
- YOLO 기반 머리 감지 및 블러 처리
- 1줄 오버레이 텍스트 (상단 좌측)
- FFmpeg 기반 MP4 저장
- 처리 통계 수집
"""

import cv2
import threading
import time
import queue
import logging
import numpy as np
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

try:
	from .config import RTSPConfig, format_gps_coordinates
	from .blur_handler import BlurHandler
	from .video_writer import VideoWriterManager
except ImportError:
	from config import RTSPConfig, format_gps_coordinates
	from blur_handler import BlurHandler
	from video_writer import VideoWriterManager

logger = logging.getLogger(__name__)

@dataclass
class ProcessingStats:
	"""프레임 처리 통계"""
	processed_frames: int = 0
	saved_frames: int = 0
	error_frames: int = 0
	blur_applied_frames: int = 0
	processing_time_total: float = 0
	
	def to_dict(self) -> dict:
		"""딕셔너리로 변환"""
		avg_processing_time = self.processing_time_total / max(self.processed_frames, 1)
		return {
			'processed_frames': self.processed_frames,
			'saved_frames': self.saved_frames,
			'error_frames': self.error_frames,
			'blur_applied_frames': self.blur_applied_frames,
			'avg_processing_time_ms': avg_processing_time * 1000,
			'save_rate': self.saved_frames / max(self.processed_frames, 1) * 100
		}

class OverlayRenderer:
	"""오버레이 렌더링 최적화"""
	
	def __init__(self, config: RTSPConfig):
		self.config = config
		self.last_text = ""
		self.last_render_time = 0
		self.render_interval = 1.0  # 1초마다 텍스트 업데이트
		self.blackbox_manager = None  # 블랙박스 매니저 참조
		
	def create_single_line_overlay(self) -> str:
		"""1줄 오버레이 텍스트 생성 (상단 좌측) - 블랙박스 데이터 반영"""
		
		# 블랙박스 데이터에서 오버레이 정보 가져오기
		if self.blackbox_manager:
			overlay_data = self.blackbox_manager.get_overlay_data()
			if overlay_data:
				# 블랙박스 데이터 사용
				vessel_name = overlay_data.vessel_name
				latitude = overlay_data.latitude
				longitude = overlay_data.longitude
				timestamp = overlay_data.timestamp
			else:
				# 블랙박스 데이터 없으면 기본값 사용
				vessel_name = self.config.overlay_config.vessel_name
				latitude = self.config.overlay_config.latitude
				longitude = self.config.overlay_config.longitude
				timestamp = datetime.now()
		else:
			# 블랙박스 매니저 없으면 기본값 사용
			vessel_name = self.config.overlay_config.vessel_name
			latitude = self.config.overlay_config.latitude
			longitude = self.config.overlay_config.longitude
			timestamp = datetime.now()
		
		# GPS 좌표를 60분법으로 변환
		lat_dms, lon_dms = format_gps_coordinates(latitude, longitude)
		
		# 시간 형식 (초단위까지 포함)
		time_str = timestamp.strftime("%y%m%d %H:%M:%S")

		# 컴팩트한 형식
		overlay_text = (
			f"{vessel_name} | S{self.config.overlay_config.stream_number:02d} | "
			f"{lat_dms} {lon_dms} | {time_str}"
		)
		
		return overlay_text
	
	def set_blackbox_manager(self, blackbox_manager):
		"""블랙박스 매니저 설정"""
		self.blackbox_manager = blackbox_manager
	
	def get_adaptive_font_settings(self, frame_width: int, frame_height: int) -> dict:
		"""해상도별 폰트 설정 자동 조정"""
		# 기준: 1920x1080
		base_width = 1920
		base_height = 1080
		
		# 스케일 팩터 계산
		width_scale = frame_width / base_width
		height_scale = frame_height / base_height
		scale_factor = min(width_scale, height_scale)
		
		return {
			"font_scale": 0.8 * scale_factor,
			"font_thickness": max(1, int(2 * scale_factor)),
			"outline_thickness": max(2, int(4 * scale_factor)),
			"margin_x": int(10 * scale_factor),
			"margin_y": int(15 * scale_factor)
		}
	
	def apply_overlay(self, frame: np.ndarray) -> np.ndarray:
		"""성능 최적화된 오버레이 렌더링"""
		current_time = time.time()
		
		# 1초마다만 텍스트 업데이트 (성능 최적화)
		if current_time - self.last_render_time >= self.render_interval:
			self.last_text = self.create_single_line_overlay()
			self.last_render_time = current_time
		
		# 캐시된 텍스트로 오버레이 적용
		return self._apply_text_overlay(frame, self.last_text)
	
	def _apply_text_overlay(self, frame: np.ndarray, overlay_text: str) -> np.ndarray:
		"""프레임에 1줄 오버레이 텍스트 적용"""
		if not overlay_text:
			return frame
		
		height, width = frame.shape[:2]
		font_settings = self.get_adaptive_font_settings(width, height)
		
		# 폰트 설정
		font = cv2.FONT_HERSHEY_SIMPLEX
		font_scale = font_settings["font_scale"]
		font_thickness = font_settings["font_thickness"]
		outline_thickness = font_settings["outline_thickness"]
		font_color = (255, 255, 255)  # 흰색
		outline_color = (0, 0, 0)     # 검은색 외곽선
		
		# 텍스트 크기 측정
		(text_width, text_height), baseline = cv2.getTextSize(
			overlay_text, font, font_scale, font_thickness
		)
		
		# 적응형 위치 설정 (상단 좌측)
		x = font_settings["margin_x"]
		y = text_height + font_settings["margin_y"]
		
		# 반투명 배경 박스 생성 (가독성 향상)
		box_coords = [
			(x - 5, y - text_height - 5),           # 좌상단
			(x + text_width + 10, y + baseline + 5)  # 우하단
		]
		
		# 배경 박스 그리기 (반투명 검은색)
		overlay = frame.copy()
		cv2.rectangle(overlay, box_coords[0], box_coords[1], (0, 0, 0), -1)
		cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)
		
		# 텍스트 외곽선 그리기 (가독성 향상)
		cv2.putText(frame, overlay_text, (x, y), font, font_scale,
				   outline_color, outline_thickness, cv2.LINE_AA)
		
		# 메인 텍스트 그리기
		cv2.putText(frame, overlay_text, (x, y), font, font_scale,
				   font_color, font_thickness, cv2.LINE_AA)
		
		return frame

class FrameProcessor(threading.Thread):
	"""프레임 처리 및 저장 전용 스레드"""
	
	def __init__(self, config: RTSPConfig, frame_queue: queue.Queue):
		super().__init__(daemon=True)
		self.config = config
		self.frame_queue = frame_queue
		self.running = False
		
		# 컴포넌트 초기화
		self.blur_handler = BlurHandler(config)
		self.video_writer = VideoWriterManager(config)
		self.overlay_renderer = OverlayRenderer(config)
		self.blackbox_manager = None
		
		# 통계
		self.stats = ProcessingStats()
		
		logger.info("FrameProcessor 초기화 완료")
	
	def set_blackbox_manager(self, blackbox_manager):
		"""블랙박스 매니저 설정"""
		self.blackbox_manager = blackbox_manager
		self.overlay_renderer.set_blackbox_manager(blackbox_manager)
		logger.info("FrameProcessor에 블랙박스 매니저 설정됨")
	
	def run(self):
		"""프레임 처리 메인 루프"""
		logger.info("프레임 처리 시작")
		self.running = True
		
		frame_timeout = 1.0  # 1초 타임아웃
		
		while self.running:
			try:
				# 큐에서 프레임 읽기 (타임아웃 포함)
				try:
					frame_data = self.frame_queue.get(timeout=frame_timeout)
					frame, timestamp = frame_data
				except queue.Empty:
					# 타임아웃 시 계속 진행
					continue
				
				# 녹화 허용 여부 확인 (속도 임계값) - 블러/저장 모두 스킵
				if self.blackbox_manager and not self.blackbox_manager.is_recording_enabled():
					if self.video_writer and self.video_writer.current_writer:
						logger.info("속도 임계 초과로 저장 중단, 현재 세그먼트 finalize")
						self.video_writer.finalize_current_video()
					self.stats.processed_frames += 1
					self.frame_queue.task_done()
					continue
				
				# 프레임 처리
				processed_frame = self.process_frame(frame)
				
				if processed_frame is not None:
					# 영상 저장
					if self.video_writer.write_frame(processed_frame):
						self.stats.saved_frames += 1
					
					self.stats.processed_frames += 1
				
				# 큐 작업 완료 표시
				self.frame_queue.task_done()
				
			except Exception as e:
				logger.error(f"프레임 처리 중 오류: {e}")
				self.stats.error_frames += 1
				
				# 큐에서 항목을 가져왔다면 task_done 호출
				try:
					self.frame_queue.task_done()
				except ValueError:
					pass  # 이미 task_done이 호출되었거나 항목이 없음
		
		# 정리
		self.cleanup()
		logger.info("프레임 처리 종료")
	
	def process_frame(self, frame: np.ndarray) -> Optional[np.ndarray]:
		"""단일 프레임 처리"""
		if frame is None:
			return None
		
		processing_start = time.time()
		
		try:
			# 1. YOLO 블러 처리 (먼저 적용)
			if self.config.blur_enabled:
				frame = self.blur_handler.apply_blur(frame)
				self.stats.blur_applied_frames += 1
			
			# 2. 1줄 오버레이 적용 (블러 처리 후)
			frame = self.overlay_renderer.apply_overlay(frame)
			
			# 처리 시간 기록
			processing_time = time.time() - processing_start
			self.stats.processing_time_total += processing_time
			
			return frame
			
		except Exception as e:
			logger.error(f"프레임 처리 오류: {e}")
			return frame  # 오류 시 원본 프레임 반환
	
	def stop(self):
		"""프레임 처리 중지"""
		logger.info("프레임 처리 중지 요청")
		self.running = False
	
	def cleanup(self):
		"""리소스 정리"""
		logger.info("프레임 프로세서 정리 시작")
		
		# 비디오 라이터 정리
		if self.video_writer:
			self.video_writer.cleanup()
		
		# 블러 핸들러 정리
		if self.blur_handler:
			self.blur_handler.cleanup()
		
		logger.info("프레임 프로세서 정리 완료")
	
	def get_stats(self) -> dict:
		"""처리 통계 반환"""
		stats = self.stats.to_dict()
		
		# 추가 정보
		stats['blur_handler_available'] = self.blur_handler.is_available() if self.blur_handler else False
		stats['video_writer_status'] = self.video_writer.get_status() if self.video_writer else {}
		stats['blur_module_info'] = self.blur_handler.get_module_info() if self.blur_handler else {}
		
		return stats
	
	def get_queue_status(self) -> dict:
		"""큐 상태 반환"""
		return {
			'queue_size': self.frame_queue.qsize(),
			'queue_maxsize': self.frame_queue.maxsize,
			'queue_full': self.frame_queue.full(),
			'queue_empty': self.frame_queue.empty()
		} 