"""RTSP 클라이언트 GUI 모듈"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk
import threading
import logging
import queue
import time
from datetime import datetime
from typing import Optional

from .config import RTSPConfig
from .processor import SharedPoolRTSPProcessor
from .statistics import FrameCounter, ResourceMonitor, PerformanceProfiler

logger = logging.getLogger(__name__)


class RTSPProcessorGUI:
    """RTSP 프로세서 GUI 클래스 - 기본 템플릿"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("RTSP 시뮬레이터")
        self.root.geometry("1200x800")
        
        self.processor = None
        self.config = None
        self.running = False
        
        self.setup_ui()
    
    def setup_ui(self):
        """기본 UI 설정"""
        # 메인 프레임
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 제목
        title_label = ttk.Label(main_frame, text="RTSP 프로세서", 
                               font=("Arial", 16, "bold"))
        title_label.pack(pady=(0, 20))
        
        # 컨트롤 프레임
        control_frame = ttk.LabelFrame(main_frame, text="제어", padding="10")
        control_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 버튼들
        button_frame = ttk.Frame(control_frame)
        button_frame.pack(fill=tk.X)
        
        self.start_button = ttk.Button(button_frame, text="시작", 
                                      command=self.start_processing)
        self.start_button.pack(side=tk.LEFT, padx=(0, 5))
        
        self.stop_button = ttk.Button(button_frame, text="중지", 
                                     command=self.stop_processing,
                                     state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=(0, 5))
        
        # 상태 프레임
        status_frame = ttk.LabelFrame(main_frame, text="상태", padding="10")
        status_frame.pack(fill=tk.BOTH, expand=True)
        
        # 상태 텍스트
        self.status_text = tk.Text(status_frame, height=20, width=80)
        self.status_text.pack(fill=tk.BOTH, expand=True)
        
        # 스크롤바
        scrollbar = ttk.Scrollbar(status_frame, orient=tk.VERTICAL, 
                                 command=self.status_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.status_text.config(yscrollcommand=scrollbar.set)
    
    def start_processing(self):
        """처리 시작"""
        try:
            # 기본 설정으로 RTSP 처리 시작
            sources = ["rtsp://example.com/stream"]  # 예시 소스
            self.config = RTSPConfig(sources=sources)
            
            self.processor = SharedPoolRTSPProcessor(self.config)
            self.processor.start()
            
            self.running = True
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            
            self.log_message("RTSP 처리 시작됨")
            
        except Exception as e:
            messagebox.showerror("오류", f"처리 시작 실패: {e}")
    
    def stop_processing(self):
        """처리 중지"""
        try:
            if self.processor:
                self.processor.stop()
                self.processor = None
            
            self.running = False
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            
            self.log_message("RTSP 처리 중지됨")
            
        except Exception as e:
            messagebox.showerror("오류", f"처리 중지 실패: {e}")
    
    def log_message(self, message: str):
        """로그 메시지 출력"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_line = f"[{timestamp}] {message}\n"
        
        self.status_text.insert(tk.END, log_line)
        self.status_text.see(tk.END)
    
    def on_closing(self):
        """윈도우 종료 처리"""
        if self.running:
            self.stop_processing()
        self.root.destroy()


def create_gui():
    """GUI 생성 함수"""
    root = tk.Tk()
    app = RTSPProcessorGUI(root)
    
    # 윈도우 종료 이벤트 처리
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    
    return root, app


if __name__ == "__main__":
    root, app = create_gui()
    root.mainloop()