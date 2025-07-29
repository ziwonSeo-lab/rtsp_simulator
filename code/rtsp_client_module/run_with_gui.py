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
        self.root.title("RTSP 시뮬레이터 - GUI 모드")
        self.root.geometry("1000x700")
        
        self.processor = None
        self.config = None
        self.running = False
        self.update_thread = None
        
        # 기본 설정값들
        self.sources = ["rtsp://example.com/stream"]
        self.thread_count = 2
        self.blur_workers = 1
        self.save_workers = 1
        self.save_enabled = False
        self.save_path = "./output/"
        
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
        title_label.pack(pady=(0, 20))
        
        # 설정 프레임
        config_frame = ttk.LabelFrame(main_frame, text="설정", padding="10")
        config_frame.pack(fill=tk.X, pady=(0, 10))
        
        # RTSP 소스 설정
        source_frame = ttk.Frame(config_frame)
        source_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(source_frame, text="RTSP 소스:").pack(side=tk.LEFT)
        self.source_entry = ttk.Entry(source_frame, width=50)
        self.source_entry.pack(side=tk.LEFT, padx=(5, 0), fill=tk.X, expand=True)
        self.source_entry.insert(0, "rtsp://example.com/stream")
        
        # 스레드 수 설정
        thread_frame = ttk.Frame(config_frame)
        thread_frame.pack(fill=tk.X, pady=(5, 5))
        
        ttk.Label(thread_frame, text="스레드 수:").pack(side=tk.LEFT)
        self.thread_var = tk.StringVar(value="2")
        thread_spin = ttk.Spinbox(thread_frame, from_=1, to=10, width=10, textvariable=self.thread_var)
        thread_spin.pack(side=tk.LEFT, padx=(5, 0))
        
        # 저장 설정
        save_frame = ttk.Frame(config_frame)
        save_frame.pack(fill=tk.X, pady=(5, 0))
        
        self.save_var = tk.BooleanVar()
        save_check = ttk.Checkbutton(save_frame, text="비디오 저장 활성화", variable=self.save_var)
        save_check.pack(side=tk.LEFT)
        
        ttk.Label(save_frame, text="저장 경로:").pack(side=tk.LEFT, padx=(20, 5))
        self.save_path_entry = ttk.Entry(save_frame, width=30)
        self.save_path_entry.pack(side=tk.LEFT, padx=(0, 5))
        self.save_path_entry.insert(0, "./output/")
        
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
        
        # 로그 프레임
        log_frame = ttk.LabelFrame(main_frame, text="로그", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        # 로그 텍스트
        log_text_frame = ttk.Frame(log_frame)
        log_text_frame.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = tk.Text(log_text_frame, height=15, width=80)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 스크롤바
        log_scrollbar = ttk.Scrollbar(log_text_frame, orient=tk.VERTICAL, 
                                     command=self.log_text.yview)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=log_scrollbar.set)
        
        # 로그 클리어 버튼
        clear_btn = ttk.Button(log_frame, text="로그 지우기", command=self.clear_log)
        clear_btn.pack(pady=(5, 0))
    
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
    
    def start_processing(self):
        """처리 시작"""
        try:
            # 설정 값 읽기
            source = self.source_entry.get().strip()
            if not source:
                messagebox.showerror("오류", "RTSP 소스를 입력해주세요.")
                return
            
            sources = [source]
            thread_count = int(self.thread_var.get())
            save_enabled = self.save_var.get()
            save_path = self.save_path_entry.get().strip()
            
            if save_enabled and not save_path:
                messagebox.showerror("오류", "저장 경로를 입력해주세요.")
                return
            
            # 설정 생성
            self.config = RTSPConfig(
                sources=sources,
                thread_count=thread_count,
                blur_workers=1,
                save_workers=1,
                save_enabled=save_enabled,
                save_path=save_path
            )
            
            # 프로세서 생성 및 시작
            self.processor = SharedPoolRTSPProcessor(self.config)
            self.processor.start()
            
            self.running = True
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            self.status_label.config(text="실행 중", foreground="green")
            
            logger.info("RTSP 처리 시작됨")
            
            # 상태 업데이트 스레드 시작
            self.start_update_thread()
            
        except Exception as e:
            messagebox.showerror("오류", f"처리 시작 실패: {e}")
            logger.error(f"처리 시작 실패: {e}")
    
    def stop_processing(self):
        """처리 중지"""
        try:
            if self.processor:
                self.processor.stop()
                self.processor = None
            
            self.running = False
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
                    # 여기에 상태 정보 업데이트 로직 추가 가능
                    pass
                time.sleep(1)
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