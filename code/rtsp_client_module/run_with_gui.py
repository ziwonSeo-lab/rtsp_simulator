#!/usr/bin/env python3
"""
RTSP 클라이언트 모듈 - GUI 포함 실행파일
"""

import sys
import os
import logging
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk
import threading
import queue
import time
from datetime import datetime
from typing import Optional
import cv2
import numpy as np

# 현재 디렉토리를 Python path에 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

try:
    from rtsp_client_module import RTSPConfig, SharedPoolRTSPProcessor
    from rtsp_client_module.statistics import FrameCounter, ResourceMonitor, PerformanceProfiler
except ImportError as e:
    print(f"모듈 임포트 오류: {e}")
    print("필요한 의존성을 설치해주세요:")
    print("pip install opencv-python numpy psutil pillow")
    sys.exit(1)

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RTSPProcessorGUI:
    """RTSP 프로세서 GUI 클래스"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("RTSP 시뮬레이터 - GUI 모드 (미리보기 지원)")
        self.root.geometry("1200x800")
        
        self.processor = None
        self.config = None
        self.running = False
        self.update_thread = None
        
        # 미리보기 관련 변수
        self.preview_enabled = True
        self.preview_frame_queue = queue.Queue(maxsize=50)  # 다중 소스를 위해 크기 증가
        self.preview_thread = None
        self.preview_canvases = {}  # 소스별 캔버스 딕셔너리
        self.preview_labels = {}    # 소스별 라벨 딕셔너리  
        self.current_preview_images = {}  # 소스별 이미지 참조 딕셔너리
        
        # config.py의 기본값 로드
        default_config = RTSPConfig()
        self.sources = default_config.sources
        self.thread_count = default_config.thread_count
        self.blur_workers = default_config.blur_workers
        self.save_workers = default_config.save_workers
        self.save_enabled = default_config.save_enabled
        self.save_path = default_config.save_path
        
        self.setup_statistics_variables()  # UI 설정 전에 변수들 초기화
        self.setup_ui()
        self.setup_logging_handler()
    
    def setup_ui(self):
        """UI 설정"""
        # 메인 프레임
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 제목
        title_label = ttk.Label(main_frame, text="RTSP 프로세서 - GUI 모드", 
                               font=("Arial", 16, "bold"))
        title_label.pack(pady=(0, 10))
        
        # 상단 컨테이너 (설정 + 미리보기)
        top_container = ttk.Frame(main_frame)
        top_container.pack(fill=tk.X, pady=(0, 10))
        
        # 설정 프레임 (왼쪽)
        config_frame = ttk.LabelFrame(top_container, text="설정", padding="10")
        config_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        # 미리보기 프레임 (오른쪽) - 동적으로 생성될 예정
        self.preview_main_frame = ttk.LabelFrame(top_container, text="실시간 미리보기", padding="5")
        self.preview_main_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 0))
        
        # 미리보기 활성화 체크박스
        self.preview_var = tk.BooleanVar(value=self.preview_enabled)
        preview_check = ttk.Checkbutton(self.preview_main_frame, text="미리보기 활성화", 
                                      variable=self.preview_var,
                                      command=self.toggle_preview)
        preview_check.pack(pady=(0, 5))
        
        # 미리보기 컨테이너 (동적 캔버스들이 들어갈 공간)
        self.preview_container = ttk.Frame(self.preview_main_frame)
        self.preview_container.pack(fill=tk.BOTH, expand=True)
        
        # RTSP 소스 설정 (다중 소스 지원)
        self.setup_sources_panel(config_frame)
        
        # 스레드 수 설정
        thread_frame = ttk.Frame(config_frame)
        thread_frame.pack(fill=tk.X, pady=(5, 5))
        
        ttk.Label(thread_frame, text="스레드 수:").pack(side=tk.LEFT)
        self.thread_var = tk.StringVar(value=str(self.thread_count))
        thread_spin = ttk.Spinbox(thread_frame, from_=1, to=10, width=10, textvariable=self.thread_var)
        thread_spin.pack(side=tk.LEFT, padx=(5, 0))
        
        # 저장 설정
        save_frame = ttk.Frame(config_frame)
        save_frame.pack(fill=tk.X, pady=(5, 0))
        
        self.save_var = tk.BooleanVar(value=self.save_enabled)
        save_check = ttk.Checkbutton(save_frame, text="비디오 저장 활성화", variable=self.save_var)
        save_check.pack(side=tk.LEFT)
        
        ttk.Label(save_frame, text="저장 경로:").pack(side=tk.LEFT, padx=(20, 5))
        self.save_path_entry = ttk.Entry(save_frame, width=30)
        self.save_path_entry.pack(side=tk.LEFT, padx=(0, 5))
        self.save_path_entry.insert(0, self.save_path)
        
        browse_btn = ttk.Button(save_frame, text="찾기", command=self.browse_save_path)
        browse_btn.pack(side=tk.LEFT)
        
        # 컨트롤 프레임
        control_frame = ttk.LabelFrame(main_frame, text="제어", padding="10")
        control_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 버튼들
        button_frame = ttk.Frame(control_frame)
        button_frame.pack(fill=tk.X)
        
        self.start_button = ttk.Button(button_frame, text="시작", 
                                      command=self.start_processing, style="Accent.TButton")
        self.start_button.pack(side=tk.LEFT, padx=(0, 5))
        
        self.stop_button = ttk.Button(button_frame, text="중지", 
                                     command=self.stop_processing,
                                     state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=(0, 5))
        
        # 상태 표시
        self.status_label = ttk.Label(button_frame, text="대기 중", foreground="blue")
        self.status_label.pack(side=tk.LEFT, padx=(20, 0))
        
        # 통계 정보 프레임
        print("DEBUG: 통계 프레임 생성 중...")  # 디버그 로그
        stats_frame = ttk.LabelFrame(main_frame, text="🔥 실시간 통계 🔥", padding="10")
        stats_frame.pack(fill=tk.X, pady=(10, 10))  # pady 증가
        stats_frame.configure(relief="solid", borderwidth=2)  # 테두리 강조
        
        print("DEBUG: setup_statistics_panel 호출 예정...")  # 디버그 로그
        self.setup_statistics_panel(stats_frame)
        print("DEBUG: setup_statistics_panel 호출 완료")  # 디버그 로그
        
        # 로그 프레임
        log_frame = ttk.LabelFrame(main_frame, text="로그", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        # 로그 텍스트
        log_text_frame = ttk.Frame(log_frame)
        log_text_frame.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = tk.Text(log_text_frame, height=8, width=80)  # 높이를 15에서 8로 축소
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 스크롤바
        log_scrollbar = ttk.Scrollbar(log_text_frame, orient=tk.VERTICAL, 
                                     command=self.log_text.yview)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=log_scrollbar.set)
        
        # 로그 클리어 버튼
        clear_btn = ttk.Button(log_frame, text="로그 지우기", command=self.clear_log)
        clear_btn.pack(pady=(5, 0))
    
    def setup_statistics_variables(self):
        """통계 관련 변수 초기화"""
        # 통계 업데이트 스레드
        self.stats_update_thread = None
        self.stats_update_interval = 1.0  # 1초마다 업데이트
        
        # 통계 데이터 저장
        self.last_stats = {}
        
        # 소스 관리 변수
        self.source_entries = []  # 소스 입력 위젯들
        self.source_frames = []   # 소스 프레임들
    
    def setup_statistics_panel(self, parent_frame):
        """통계 정보 패널 설정"""
        print("DEBUG: setup_statistics_panel 호출됨")  # 디버그 로그
        
        # 통계 컨테이너를 3개 열로 분할
        stats_container = ttk.Frame(parent_frame)
        stats_container.pack(fill=tk.X, expand=True)
        
        print("DEBUG: stats_container 생성됨")  # 디버그 로그
        
        # 테스트용 간단한 라벨 추가
        test_label = ttk.Label(stats_container, text="[TEST] 통계 패널이 보이시나요?", 
                              font=("Arial", 12, "bold"), foreground="red")
        test_label.pack(pady=10)
        
        # 왼쪽: 프레임 통계
        frame_stats_frame = ttk.LabelFrame(stats_container, text="프레임 통계", padding="5")
        frame_stats_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        # 수신 프레임
        ttk.Label(frame_stats_frame, text="수신:").grid(row=0, column=0, sticky='w', padx=(0, 5))
        self.received_frames_label = ttk.Label(frame_stats_frame, text="0", foreground="blue")
        self.received_frames_label.grid(row=0, column=1, sticky='w')
        
        # 처리 프레임
        ttk.Label(frame_stats_frame, text="처리:").grid(row=1, column=0, sticky='w', padx=(0, 5))
        self.processed_frames_label = ttk.Label(frame_stats_frame, text="0", foreground="green")
        self.processed_frames_label.grid(row=1, column=1, sticky='w')
        
        # 저장 프레임
        ttk.Label(frame_stats_frame, text="저장:").grid(row=2, column=0, sticky='w', padx=(0, 5))
        self.saved_frames_label = ttk.Label(frame_stats_frame, text="0", foreground="purple")
        self.saved_frames_label.grid(row=2, column=1, sticky='w')
        
        # 손실 프레임
        ttk.Label(frame_stats_frame, text="손실:").grid(row=3, column=0, sticky='w', padx=(0, 5))
        self.lost_frames_label = ttk.Label(frame_stats_frame, text="0", foreground="red")
        self.lost_frames_label.grid(row=3, column=1, sticky='w')
        
        # 중간: 성능 지표
        performance_stats_frame = ttk.LabelFrame(stats_container, text="성능 지표", padding="5")
        performance_stats_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 5))
        
        # 처리율
        ttk.Label(performance_stats_frame, text="처리율:").grid(row=0, column=0, sticky='w', padx=(0, 5))
        self.processing_rate_label = ttk.Label(performance_stats_frame, text="0.0%", foreground="green")
        self.processing_rate_label.grid(row=0, column=1, sticky='w')
        
        # 손실율
        ttk.Label(performance_stats_frame, text="손실율:").grid(row=1, column=0, sticky='w', padx=(0, 5))
        self.loss_rate_label = ttk.Label(performance_stats_frame, text="0.0%", foreground="red")
        self.loss_rate_label.grid(row=1, column=1, sticky='w')
        
        # 저장율
        ttk.Label(performance_stats_frame, text="저장율:").grid(row=2, column=0, sticky='w', padx=(0, 5))
        self.save_rate_label = ttk.Label(performance_stats_frame, text="0.0%", foreground="purple")
        self.save_rate_label.grid(row=2, column=1, sticky='w')
        
        # FPS
        ttk.Label(performance_stats_frame, text="FPS:").grid(row=3, column=0, sticky='w', padx=(0, 5))
        self.fps_label = ttk.Label(performance_stats_frame, text="0.0", foreground="blue")
        self.fps_label.grid(row=3, column=1, sticky='w')
        
        # 오른쪽: 시스템 리소스
        resource_stats_frame = ttk.LabelFrame(stats_container, text="시스템 리소스", padding="5")
        resource_stats_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        # CPU 사용률
        ttk.Label(resource_stats_frame, text="CPU:").grid(row=0, column=0, sticky='w', padx=(0, 5))
        self.cpu_usage_label = ttk.Label(resource_stats_frame, text="0.0%", foreground="orange")
        self.cpu_usage_label.grid(row=0, column=1, sticky='w')
        
        # RAM 사용률
        ttk.Label(resource_stats_frame, text="RAM:").grid(row=1, column=0, sticky='w', padx=(0, 5))
        self.ram_usage_label = ttk.Label(resource_stats_frame, text="0.0%", foreground="orange")
        self.ram_usage_label.grid(row=1, column=1, sticky='w')
        
        # GPU 사용률 (사용 가능한 경우)
        ttk.Label(resource_stats_frame, text="GPU:").grid(row=2, column=0, sticky='w', padx=(0, 5))
        self.gpu_usage_label = ttk.Label(resource_stats_frame, text="N/A", foreground="gray")
        self.gpu_usage_label.grid(row=2, column=1, sticky='w')
        
        # 큐 크기
        ttk.Label(resource_stats_frame, text="큐:").grid(row=3, column=0, sticky='w', padx=(0, 5))
        self.queue_size_label = ttk.Label(resource_stats_frame, text="0/0/0", foreground="brown")
        self.queue_size_label.grid(row=3, column=1, sticky='w')
    
    def setup_sources_panel(self, parent_frame):
        """RTSP 소스 패널 설정"""
        # 소스 설정 프레임
        sources_frame = ttk.LabelFrame(parent_frame, text="RTSP 소스 목록", padding="5")
        sources_frame.pack(fill=tk.X, pady=(0, 5))
        
        # 소스 컨테이너 (스크롤 가능)
        canvas = tk.Canvas(sources_frame, height=120)
        scrollbar = ttk.Scrollbar(sources_frame, orient="vertical", command=canvas.yview)
        self.sources_scrollable_frame = ttk.Frame(canvas)
        
        self.sources_scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.sources_scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 초기 소스들 로드
        self.load_initial_sources()
        
        # 소스 추가/삭제 버튼
        button_frame = ttk.Frame(sources_frame)
        button_frame.pack(fill=tk.X, pady=(5, 0))
        
        add_btn = ttk.Button(button_frame, text="소스 추가", command=self.add_source_entry)
        add_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        remove_btn = ttk.Button(button_frame, text="소스 삭제", command=self.remove_source_entry)
        remove_btn.pack(side=tk.LEFT)
    
    def load_initial_sources(self):
        """초기 소스들 로드"""
        # config.py의 기본 소스들을 로드
        for i, source in enumerate(self.sources):
            self.add_source_entry(source)
            
        # 최소 하나의 소스는 있어야 함
        if not self.source_entries:
            self.add_source_entry("rtsp://example.com/stream")
    
    def add_source_entry(self, initial_value=""):
        """새 소스 입력 추가"""
        frame = ttk.Frame(self.sources_scrollable_frame)
        frame.pack(fill=tk.X, pady=2)
        
        # 소스 번호 라벨
        source_num = len(self.source_entries) + 1
        ttk.Label(frame, text=f"소스 {source_num}:", width=8).pack(side=tk.LEFT)
        
        # 소스 입력 필드
        entry = ttk.Entry(frame, width=50)
        entry.pack(side=tk.LEFT, padx=(5, 0), fill=tk.X, expand=True)
        
        if initial_value:
            entry.insert(0, initial_value)
        
        self.source_entries.append(entry)
        self.source_frames.append(frame)
        
        # 미리보기 캔버스도 업데이트
        self.update_preview_canvases()
    
    def remove_source_entry(self):
        """마지막 소스 입력 제거"""
        if len(self.source_entries) > 1:  # 최소 하나는 유지
            # 마지막 항목 제거
            last_entry = self.source_entries.pop()
            last_frame = self.source_frames.pop()
            
            last_frame.destroy()
            
            # 미리보기 캔버스도 업데이트
            self.update_preview_canvases()
    
    def get_sources_from_entries(self):
        """입력 필드에서 소스 목록 가져오기"""
        sources = []
        for entry in self.source_entries:
            source = entry.get().strip()
            if source:  # 빈 문자열이 아닌 경우만 추가
                sources.append(source)
        return sources
    
    def update_preview_canvases(self):
        """소스 개수에 따라 미리보기 캔버스 업데이트"""
        # 기존 캔버스들 제거
        for widget in self.preview_container.winfo_children():
            widget.destroy()
        
        self.preview_canvases.clear()
        self.preview_labels.clear()
        self.current_preview_images.clear()
        
        # 현재 소스 개수 확인
        source_count = len(self.source_entries)
        
        if source_count == 0:
            return
        
        # 그리드 레이아웃 계산 (최대 2열)
        cols = min(2, source_count)
        rows = (source_count + cols - 1) // cols
        
        # 캔버스 크기 계산
        canvas_width = 200 if source_count > 1 else 320
        canvas_height = 150 if source_count > 1 else 240
        
        for i in range(source_count):
            # 캔버스 프레임
            canvas_frame = ttk.Frame(self.preview_container)
            row = i // cols
            col = i % cols
            canvas_frame.grid(row=row, column=col, padx=2, pady=2, sticky="nsew")
            
            # 소스 라벨
            source_label = ttk.Label(canvas_frame, text=f"소스 {i+1}", 
                                   font=("Arial", 8, "bold"))
            source_label.pack()
            
            # 미리보기 캔버스
            canvas = tk.Canvas(canvas_frame, width=canvas_width, height=canvas_height, bg="black")
            canvas.pack(padx=2, pady=2)
            
            # 상태 라벨
            status_label = ttk.Label(canvas_frame, text="대기 중", font=("Arial", 7))
            status_label.pack()
            
            # 딕셔너리에 저장
            stream_id = f"stream_{i+1}"
            self.preview_canvases[stream_id] = canvas
            self.preview_labels[stream_id] = status_label
            self.current_preview_images[stream_id] = None
        
        # 그리드 가중치 설정
        for i in range(cols):
            self.preview_container.columnconfigure(i, weight=1)
        for i in range(rows):
            self.preview_container.rowconfigure(i, weight=1)
    
    def setup_logging_handler(self):
        """로그 핸들러 설정"""
        class TextHandler(logging.Handler):
            def __init__(self, text_widget):
                super().__init__()
                self.text_widget = text_widget
            
            def emit(self, record):
                try:
                    msg = self.format(record)
                    self.text_widget.insert(tk.END, msg + '\n')
                    self.text_widget.see(tk.END)
                    self.text_widget.update_idletasks()
                except:
                    pass
        
        handler = TextHandler(self.log_text)
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logging.getLogger().addHandler(handler)
    
    def browse_save_path(self):
        """저장 경로 찾기"""
        path = filedialog.askdirectory(initialdir=self.save_path_entry.get())
        if path:
            self.save_path_entry.delete(0, tk.END)
            self.save_path_entry.insert(0, path)
    
    def toggle_preview(self):
        """미리보기 활성화/비활성화 토글"""
        self.preview_enabled = self.preview_var.get()
        if not self.preview_enabled:
            # 미리보기 비활성화 시 모든 캔버스 클리어
            for stream_id, canvas in self.preview_canvases.items():
                canvas.delete("all")
                if stream_id in self.preview_labels:
                    self.preview_labels[stream_id].config(text="비활성화")
            self.current_preview_images.clear()
        else:
            # 미리보기 활성화 시 상태 초기화
            for stream_id, label in self.preview_labels.items():
                label.config(text="대기 중")
    
    def update_preview_frame(self, frame):
        """미리보기 프레임 업데이트"""
        if not self.preview_enabled or frame is None:
            return
        
        try:
            # 프레임을 큐에 추가 (최신 프레임만 유지)
            if not self.preview_frame_queue.full():
                self.preview_frame_queue.put(frame, block=False)
            else:
                # 큐가 가득 찬 경우 오래된 프레임 제거 후 새 프레임 추가
                try:
                    self.preview_frame_queue.get_nowait()
                except queue.Empty:
                    pass
                try:
                    self.preview_frame_queue.put(frame, block=False)
                except queue.Full:
                    pass
        except Exception as e:
            logger.error(f"미리보기 프레임 업데이트 오류: {e}")
    
    def process_preview_frames(self):
        """미리보기 프레임 처리 스레드"""
        while self.running and self.preview_enabled:
            try:
                # 큐에서 프레임 데이터 가져오기 (타임아웃 1초)
                frame_data = self.preview_frame_queue.get(timeout=1.0)
                
                if frame_data is not None:
                    # 프레임 데이터는 (stream_id, frame, info) 튜플 형태
                    if isinstance(frame_data, tuple) and len(frame_data) >= 3:
                        stream_id, frame, info = frame_data[:3]
                        
                        # 해당 스트림의 캔버스가 존재하는지 확인
                        if stream_id in self.preview_canvases:
                            # OpenCV 프레임을 PIL Image로 변환
                            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                            
                            # 미리보기 크기에 맞게 리사이즈
                            canvas = self.preview_canvases[stream_id]
                            canvas_width = canvas.winfo_width()
                            canvas_height = canvas.winfo_height()
                            
                            if canvas_width > 1 and canvas_height > 1:  # 캔버스가 초기화된 경우
                                frame_resized = cv2.resize(frame_rgb, (canvas_width, canvas_height))
                                
                                # PIL Image로 변환
                                pil_image = Image.fromarray(frame_resized)
                                tk_image = ImageTk.PhotoImage(pil_image)
                                
                                # GUI 스레드에서 캔버스 업데이트
                                self.root.after(0, self._update_canvas, stream_id, tk_image)
                                
                                # 현재 시간 업데이트
                                current_time = datetime.now().strftime("%H:%M:%S")
                                self.root.after(0, self._update_preview_label, stream_id, current_time)
                
            except queue.Empty:
                # 타임아웃 - 정상적인 상황
                continue
            except Exception as e:
                logger.error(f"미리보기 처리 오류: {e}")
                time.sleep(0.1)
    
    def _update_canvas(self, stream_id, tk_image):
        """GUI 스레드에서 캔버스 업데이트"""
        try:
            if stream_id in self.preview_canvases:
                canvas = self.preview_canvases[stream_id]
                canvas.delete("all")
                canvas.create_image(
                    canvas.winfo_width() // 2,
                    canvas.winfo_height() // 2,
                    image=tk_image
                )
                # 이미지 참조 유지 (가비지 컬렉션 방지)
                self.current_preview_images[stream_id] = tk_image
        except Exception as e:
            logger.error(f"캔버스 업데이트 오류 ({stream_id}): {e}")
    
    def _update_preview_label(self, stream_id, time_text):
        """GUI 스레드에서 미리보기 라벨 업데이트"""
        try:
            if stream_id in self.preview_labels:
                self.preview_labels[stream_id].config(text=f"실시간 ({time_text})")
        except Exception as e:
            logger.error(f"미리보기 라벨 업데이트 오류 ({stream_id}): {e}")
    
    def start_preview_thread(self):
        """미리보기 스레드 시작"""
        if self.preview_enabled and (self.preview_thread is None or not self.preview_thread.is_alive()):
            self.preview_thread = threading.Thread(target=self.process_preview_frames, daemon=True)
            self.preview_thread.start()
            logger.info("미리보기 스레드 시작됨")
    
    def stop_preview_thread(self):
        """미리보기 스레드 중지"""
        self.preview_enabled = False
        if self.preview_thread and self.preview_thread.is_alive():
            try:
                self.preview_thread.join(timeout=2.0)
            except:
                pass
        
        # 큐 비우기
        while not self.preview_frame_queue.empty():
            try:
                self.preview_frame_queue.get_nowait()
            except queue.Empty:
                break
        
        # 모든 캔버스 클리어
        for stream_id, canvas in self.preview_canvases.items():
            canvas.delete("all")
            if stream_id in self.preview_labels:
                self.preview_labels[stream_id].config(text="미리보기: 중지됨")
        self.current_preview_images.clear()
        logger.info("미리보기 스레드 중지됨")
    
    def update_statistics_display(self, stats):
        """통계 정보 UI 업데이트"""
        try:
            # 프레임 통계
            self.received_frames_label.config(text=str(stats.get('received_frames', 0)))
            self.processed_frames_label.config(text=str(stats.get('processed_frames', 0)))
            self.saved_frames_label.config(text=str(stats.get('saved_frames', 0)))
            self.lost_frames_label.config(text=str(stats.get('lost_frames', 0)))
            
            # 성능 지표
            processing_rate = stats.get('processing_rate', 0.0)
            loss_rate = stats.get('loss_rate', 0.0)
            save_rate = stats.get('save_rate', 0.0)
            
            self.processing_rate_label.config(text=f"{processing_rate:.1f}%")
            self.loss_rate_label.config(text=f"{loss_rate:.1f}%")
            self.save_rate_label.config(text=f"{save_rate:.1f}%")
            
            # FPS 계산 (새로운 프레임 수 / 시간 간격)
            current_time = time.time()
            if hasattr(self, 'last_stats_time') and hasattr(self, 'last_received_frames'):
                time_diff = current_time - self.last_stats_time
                frame_diff = stats.get('received_frames', 0) - self.last_received_frames
                fps = frame_diff / max(time_diff, 0.1)
                self.fps_label.config(text=f"{fps:.1f}")
            else:
                self.fps_label.config(text="0.0")
            
            self.last_stats_time = current_time
            self.last_received_frames = stats.get('received_frames', 0)
            
            # 시스템 리소스
            resource_stats = stats.get('resource_stats', {})
            cpu_usage = resource_stats.get('cpu_percent', 0.0)
            memory_usage = resource_stats.get('memory_percent', 0.0)
            
            self.cpu_usage_label.config(text=f"{cpu_usage:.1f}%")
            self.ram_usage_label.config(text=f"{memory_usage:.1f}%")
            
            # GPU 사용률 (사용 가능한 경우)
            gpu_usage = resource_stats.get('gpu_percent')
            if gpu_usage is not None:
                self.gpu_usage_label.config(text=f"{gpu_usage:.1f}%", foreground="orange")
            else:
                self.gpu_usage_label.config(text="N/A", foreground="gray")
            
            # 큐 크기 (blur/save/preview)
            blur_queue_size = stats.get('blur_queue_size', 0)
            save_queue_size = stats.get('save_queue_size', 0)
            preview_queue_size = stats.get('preview_queue_sizes', {}).get(0, 0)
            
            self.queue_size_label.config(text=f"{blur_queue_size}/{save_queue_size}/{preview_queue_size}")
            
        except Exception as e:
            logger.error(f"통계 UI 업데이트 오류: {e}")
    
    def start_statistics_update(self):
        """통계 업데이트 스레드 시작"""
        if self.stats_update_thread and self.stats_update_thread.is_alive():
            return
        
        self.stats_update_thread = threading.Thread(target=self.statistics_update_loop, daemon=True)
        self.stats_update_thread.start()
        logger.info("통계 업데이트 스레드 시작됨")
    
    def statistics_update_loop(self):
        """통계 업데이트 루프"""
        while self.running:
            try:
                if self.processor:
                    # 프로세서에서 통계 가져오기
                    stats = self.processor.get_statistics()
                    
                    # GUI 스레드에서 UI 업데이트
                    self.root.after(0, self.update_statistics_display, stats)
                
                time.sleep(self.stats_update_interval)
                
            except Exception as e:
                logger.error(f"통계 업데이트 루프 오류: {e}")
                time.sleep(self.stats_update_interval)
    
    def stop_statistics_update(self):
        """통계 업데이트 스레드 중지"""
        if self.stats_update_thread and self.stats_update_thread.is_alive():
            try:
                self.stats_update_thread.join(timeout=2.0)
            except:
                pass
        logger.info("통계 업데이트 스레드 중지됨")
    
    def start_processing(self):
        """처리 시작"""
        try:
            # 다중 소스 설정 값 읽기
            sources = self.get_sources_from_entries()
            if not sources:
                messagebox.showerror("오류", "최소 하나의 RTSP 소스를 입력해주세요.")
                return
            thread_count = int(self.thread_var.get())
            
            # 스레드 수가 소스 수보다 적으면 자동 조정
            if thread_count < len(sources):
                thread_count = len(sources)
                self.thread_var.set(str(thread_count))
                logger.info(f"스레드 수를 소스 수에 맞춰 {thread_count}개로 자동 조정")
            
            save_enabled = self.save_var.get()
            save_path = self.save_path_entry.get().strip()
            
            if save_enabled and not save_path:
                messagebox.showerror("오류", "저장 경로를 입력해주세요.")
                return
            
            # config.py 기본값으로 설정 생성 후 GUI 값으로 오버라이드
            self.config = RTSPConfig()
            self.config.sources = sources
            self.config.thread_count = thread_count
            self.config.save_enabled = save_enabled
            self.config.save_path = save_path
            
            # 미리보기 설정
            self.config.preview_enabled = self.preview_enabled
            
            # 프로세서 생성 및 시작
            self.processor = SharedPoolRTSPProcessor(self.config)
            self.processor.start()
            
            self.running = True
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            self.status_label.config(text="실행 중", foreground="green")
            
            logger.info("RTSP 처리 시작됨")
            
            # 미리보기 스레드 시작
            if self.preview_enabled:
                self.start_preview_thread()
            
            # 통계 업데이트 스레드 시작
            self.start_statistics_update()
            
            # 상태 업데이트 스레드 시작
            self.start_update_thread()
            
        except Exception as e:
            messagebox.showerror("오류", f"처리 시작 실패: {e}")
            logger.error(f"처리 시작 실패: {e}")
    
    def stop_processing(self):
        """처리 중지"""
        try:
            self.running = False
            
            # 미리보기 스레드 중지
            self.stop_preview_thread()
            
            # 통계 업데이트 스레드 중지
            self.stop_statistics_update()
            
            if self.processor:
                self.processor.stop()
                self.processor = None
            
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            self.status_label.config(text="중지됨", foreground="red")
            
            logger.info("RTSP 처리 중지됨")
            
        except Exception as e:
            messagebox.showerror("오류", f"처리 중지 실패: {e}")
            logger.error(f"처리 중지 실패: {e}")
    
    def start_update_thread(self):
        """상태 업데이트 스레드 시작"""
        if self.update_thread and self.update_thread.is_alive():
            return
        
        self.update_thread = threading.Thread(target=self.update_status, daemon=True)
        self.update_thread.start()
    
    def update_status(self):
        """상태 업데이트"""
        while self.running:
            try:
                if self.processor:
                    # 미리보기 프레임 가져오기 시도
                    if self.preview_enabled and hasattr(self.processor, 'get_preview_frame'):
                        try:
                            preview_frame = self.processor.get_preview_frame()
                            if preview_frame is not None:
                                self.update_preview_frame(preview_frame)
                        except Exception as e:
                            logger.debug(f"미리보기 프레임 가져오기 실패: {e}")
                    
                    # 여기에 다른 상태 정보 업데이트 로직 추가 가능
                    pass
                time.sleep(0.1)  # 미리보기를 위해 더 빠른 업데이트
            except Exception as e:
                logger.error(f"상태 업데이트 오류: {e}")
                break
    
    def clear_log(self):
        """로그 지우기"""
        self.log_text.delete(1.0, tk.END)
    
    def on_closing(self):
        """윈도우 종료 처리"""
        if self.running:
            result = messagebox.askyesno("확인", "처리가 실행 중입니다. 정말 종료하시겠습니까?")
            if not result:
                return
            self.stop_processing()
        
        # 미리보기 스레드 완전 정리
        self.stop_preview_thread()
        
        # 통계 업데이트 스레드 완전 정리
        self.stop_statistics_update()
        
        self.root.destroy()


def main():
    """메인 함수"""
    print("RTSP 클라이언트 모듈 - GUI 모드 시작")
    
    # Tkinter 루트 생성
    root = tk.Tk()
    
    # 스타일 설정
    style = ttk.Style()
    try:
        style.theme_use('clam')
    except:
        pass
    
    # GUI 앱 생성
    app = RTSPProcessorGUI(root)
    
    # 윈도우 종료 이벤트 처리
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    
    # GUI 실행
    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("\n키보드 인터럽트로 종료")
        app.on_closing()


if __name__ == "__main__":
    main()