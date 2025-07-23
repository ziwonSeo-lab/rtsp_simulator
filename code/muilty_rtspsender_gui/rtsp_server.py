"""
고급 멀티프로세스 RTSP 영상 송출 프로그램

주요 기능:
- 여러 영상 파일을 스레드 수에 따라 자동 분배
- 각 스트림별 독립 프로세스 및 PID 표시
- GUI를 통한 파일 선택 및 제어
- 실시간 상태 모니터링
- MediaMTX 기반 RTSP 송출

요구사항:
- FFmpeg 설치 필요
- MediaMTX 설치 권장
- python-opencv (cv2)
- tkinter (GUI)
"""

import os
import sys
import subprocess
import time
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import multiprocessing as mp
from multiprocessing import Process, Event, Queue, Manager
import logging
from datetime import datetime
from pathlib import Path
import json
import socket
import tempfile

# netifaces는 선택적 import
try:
    import netifaces
except ImportError:
    netifaces = None

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RTSPStreamConfig:
    """RTSP 스트림 설정 클래스"""
    def __init__(self):
        self.video_file = ""
        self.video_files = []  # 여러 파일 순환 재생용
        self.rtsp_url = ""
        self.rtsp_port = 8554  # 기본 포트
        self.fps = 15
        self.width = 1920
        self.height = 1080
        self.bitrate = "2M"
        self.codec = "libx264"
        self.preset = "fast"
        self.loop_enabled = True
        self.enabled = False
        self.stream_type = "rtsp"  # "rtsp" 또는 "udp"

def get_local_ip():
    """로컬 네트워크 IP 주소 가져오기"""
    try:
        if netifaces:
            interfaces = netifaces.interfaces()
            for interface in interfaces:
                addresses = netifaces.ifaddresses(interface)
                if netifaces.AF_INET in addresses:
                    for addr_info in addresses[netifaces.AF_INET]:
                        ip = addr_info['addr']
                        if not ip.startswith('127.') and not ip.startswith('169.254.'):
                            return ip
    except Exception:
        pass
    
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        pass
    
    return "127.0.0.1"

def get_all_network_interfaces():
    """모든 네트워크 인터페이스 IP 주소 목록 가져오기"""
    ip_list = ["127.0.0.1"]
    
    try:
        if netifaces:
            interfaces = netifaces.interfaces()
            for interface in interfaces:
                addresses = netifaces.ifaddresses(interface)
                if netifaces.AF_INET in addresses:
                    for addr_info in addresses[netifaces.AF_INET]:
                        ip = addr_info['addr']
                        if ip not in ip_list:
                            ip_list.append(ip)
    except Exception:
        pass
    
    if len(ip_list) == 1:
        try:
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            if local_ip not in ip_list:
                ip_list.append(local_ip)
        except Exception:
            pass
    
    return ip_list

def check_ffmpeg():
    """FFmpeg 설치 확인"""
    try:
        result = subprocess.run(['ffmpeg', '-version'], 
                              capture_output=True, text=True, timeout=5)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False

def check_mediamtx():
    """MediaMTX 설치 확인"""
    try:
        result = subprocess.run(['mediamtx', '--version'], 
                              capture_output=True, text=True, timeout=5)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False

def rtsp_sender_process(stream_id, config, status_queue, stop_event):
    """RTSP 송출 프로세스"""
    logger = logging.getLogger(f"RTSP_SENDER_{stream_id}")
    current_pid = os.getpid()
    logger.info(f"RTSP 송출 프로세스 시작 - PID: {current_pid}")
    
    # PID 정보를 상태 큐에 전송
    status_queue.put((stream_id, 'pid', current_pid))
    
    # 재생할 파일 목록 확인
    files_to_play = config.video_files if config.video_files else [config.video_file]
    
    if not files_to_play or not any(os.path.exists(f) for f in files_to_play):
        logger.error(f"재생 가능한 비디오 파일이 없습니다: {files_to_play}")
        status_queue.put((stream_id, 'error', f"재생 가능한 파일 없음"))
        return
    
    # 존재하는 파일만 필터링
    valid_files = [f for f in files_to_play if os.path.exists(f)]
    port = config.rtsp_port
    
    try:
        # 파일 목록을 concat 파일로 생성
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            for file_path in valid_files:
                normalized_path = file_path.replace('\\', '/')
                f.write(f"file '{normalized_path}'\n")
            concat_file = f.name
        
        logger.info(f"Concat 파일 생성: {concat_file} (파일 수: {len(valid_files)})")
        
        # 순환 파일 목록 로그 출력
        for idx, file_path in enumerate(valid_files):
            logger.info(f"  파일 {idx+1}: {os.path.basename(file_path)}")
        
        # 스트리밍 방식 선택
        if config.stream_type == "rtsp":
            # MediaMTX 방식: FFmpeg → RTMP → MediaMTX → RTSP
            rtmp_port = 1935 + stream_id  # 각 스트림별 RTMP 포트
            rtsp_port = port              # 각 스트림별 RTSP 포트
            
            # MediaMTX 연결 상태 사전 확인
            mediamtx_ready = False
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(2)
                    result = s.connect_ex(('127.0.0.1', rtmp_port))
                    mediamtx_ready = (result == 0)
            except:
                pass
            
            if not mediamtx_ready:
                logger.error(f"MediaMTX 인스턴스 {stream_id}가 RTMP 포트 {rtmp_port}에서 대기하지 않습니다!")
                logger.error(f"start_all_mediamtx.bat을 먼저 실행하세요.")
                status_queue.put((stream_id, 'error', f"MediaMTX 포트 {rtmp_port} 연결 불가"))
                return
            
            cmd = [
                'ffmpeg', '-y',
                '-f', 'concat',
                '-safe', '0',
                '-stream_loop', '-1',
                '-re',
                '-i', concat_file,
                
                # 비디오 인코딩 설정
                '-c:v', 'libx264',
                '-preset', 'ultrafast',
                '-tune', 'zerolatency',
                '-profile:v', 'baseline',
                '-level', '3.1',
                
                # 비트레이트 설정
                '-b:v', config.bitrate,
                '-maxrate', config.bitrate,
                '-bufsize', f"{int(config.bitrate[:-1]) * 2}M",
                
                # 프레임 설정
                '-r', str(config.fps),
                '-g', str(config.fps),
                '-keyint_min', str(config.fps),
                
                # 픽셀 포맷
                '-pix_fmt', 'yuv420p',
                
                # 오디오 비활성화
                '-an',
                
                # RTMP 출력
                '-f', 'flv',
                f'rtmp://127.0.0.1:{rtmp_port}/live'
            ]
            
            protocol_name = f"RTSP-MediaMTX-{stream_id}"
            connection_url = f"rtsp://127.0.0.1:{rtsp_port}/live"
            
            logger.info(f"MediaMTX 개별 인스턴스 모드 (연결 확인됨):")
            logger.info(f"  FFmpeg → RTMP:{rtmp_port} → MediaMTX:{stream_id} → RTSP:{rtsp_port}")
            
        else:  # UDP 모드
            cmd = [
                'ffmpeg', '-y',
                '-f', 'concat',
                '-safe', '0',
                '-stream_loop', '-1',
                '-re',
                '-i', concat_file,
                
                # 비디오 설정
                '-c:v', 'libx264',
                '-preset', 'ultrafast',
                '-tune', 'zerolatency',
                '-profile:v', 'baseline',
                '-b:v', config.bitrate,
                '-r', str(config.fps),
                '-g', str(config.fps),
                '-pix_fmt', 'yuv420p',
                '-an',
                
                # UDP 출력
                '-f', 'mpegts',
                f'udp://127.0.0.1:{port}?pkt_size=1316'
            ]
            protocol_name = "UDP"
            connection_url = f"udp://@127.0.0.1:{port}"
        
        logger.info(f"스트림 {stream_id} {protocol_name} 스트리밍 시작 (포트 {port})")
        logger.info(f"VLC 연결 URL: {connection_url}")
        logger.info(f"FFmpeg 명령: {' '.join(cmd)}")
        
        # FFmpeg 프로세스 시작
        ffmpeg_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )
        
        status_queue.put((stream_id, 'running', 
                        f"PID:{current_pid} | {protocol_name}:{port} | 파일:{len(valid_files)}개"))
        
        start_time = time.time()
        server_ready = False
        
        # 서버 시작 대기 및 모니터링
        while not stop_event.is_set():
            try:
                output = ffmpeg_process.stdout.readline()
                if output:
                    output = output.strip()
                    
                    # 스트리밍 시작 감지
                    if 'frame=' in output and not server_ready:
                        logger.info(f"스트림 {stream_id} {protocol_name} 스트리밍 시작됨")
                        server_ready = True
                        status_queue.put((stream_id, 'ready', f"{protocol_name} 스트리밍 준비됨: {port}"))
                    
                    # 주요 정보만 로그
                    if any(keyword in output.lower() for keyword in ['error', 'failed', 'invalid']):
                        logger.warning(f"스트림 {stream_id}: {output}")
                    elif 'frame=' in output and int(time.time()) % 10 == 0:
                        logger.info(f"스트림 {stream_id}: {output}")
                            
            except Exception as e:
                logger.error(f"출력 읽기 오류: {e}")
            
            # 프로세스 상태 확인
            poll_result = ffmpeg_process.poll()
            if poll_result is not None:
                logger.error(f"스트림 {stream_id} FFmpeg 종료됨 (코드: {poll_result})")
                
                try:
                    remaining = ffmpeg_process.stdout.read()
                    if remaining:
                        logger.error(f"스트림 {stream_id} 최종 출력:\n{remaining}")
                except:
                    pass
                
                status_queue.put((stream_id, 'error', f"FFmpeg 종료 (코드: {poll_result})"))
                break
            
            # 주기적 상태 업데이트
            runtime = time.time() - start_time
            if int(runtime) % 30 == 0:
                status_text = f"PID:{current_pid} | {protocol_name}:{port} | 실행:{runtime:.0f}초"
                if server_ready:
                    status_text += " | 스트리밍 중"
                status_queue.put((stream_id, 'running', status_text))
            
            time.sleep(0.1)
            
    except Exception as e:
        logger.error(f"스트리밍 오류: {e}")
        status_queue.put((stream_id, 'error', str(e)))
    
    finally:
        # 프로세스 정리
        try:
            if 'ffmpeg_process' in locals() and ffmpeg_process:
                if ffmpeg_process.poll() is None:
                    logger.info(f"스트림 {stream_id} FFmpeg 프로세스 종료 중...")
                    ffmpeg_process.terminate()
                    try:
                        ffmpeg_process.wait(timeout=10)
                        logger.info(f"FFmpeg 프로세스 정상 종료 (PID: {current_pid})")
                    except subprocess.TimeoutExpired:
                        logger.warning(f"FFmpeg 프로세스 강제 종료 (PID: {current_pid})")
                        ffmpeg_process.kill()
                        ffmpeg_process.wait()
        except Exception as e:
            logger.error(f"FFmpeg 프로세스 종료 오류: {e}")
        
        # 임시 파일 정리
        try:
            if 'concat_file' in locals():
                os.unlink(concat_file)
                logger.info(f"임시 파일 삭제: {concat_file}")
        except Exception as e:
            logger.warning(f"임시 파일 삭제 실패: {e}")
        
        status_queue.put((stream_id, 'stopped', f"송출 중지됨 (PID: {current_pid})"))
        logger.info(f"스트리밍 프로세스 종료완료 - PID: {current_pid}")

class RTSPSenderGUI:
    """RTSP 송출 GUI 클래스"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("고급 RTSP 영상 송출 프로그램 (RTSP 지원)")
        self.root.geometry("1600x1000")
        
        # 네트워크 설정
        self.current_ip = get_local_ip()
        self.available_ips = get_all_network_interfaces()
        
        # 데이터 구조
        self.stream_configs = [RTSPStreamConfig() for _ in range(6)]
        self.processes = {}
        self.stop_events = {}
        self.status_queues = {}
        self.stream_pids = {}
        self.manager = Manager()
        
        # 입력 파일 목록
        self.input_files = []
        
        # GUI 요소들
        self.stream_frames = []
        self.status_labels = []
        self.file_vars = []
        self.rtsp_vars = []
        self.enable_vars = []
        self.stream_type_vars = []
        
        # 모니터링
        self.monitoring = False
        self.monitor_thread = None
        
        self.setup_ui()
        self.start_monitoring()
        
        # FFmpeg 확인
        if not check_ffmpeg():
            messagebox.showerror("오류", "FFmpeg가 설치되지 않았습니다.\n프로그램이 정상 동작하지 않을 수 있습니다.")
    
    def distribute_files_to_threads(self, files, thread_count):
        """파일을 스레드 수에 따라 분배"""
        if not files or thread_count <= 0:
            return []
        
        distribution = [[] for _ in range(thread_count)]
        
        if len(files) >= thread_count:
            # 파일 개수가 스레드 개수보다 많거나 같은 경우: 순환 분배
            for i, file in enumerate(files):
                thread_index = i % thread_count
                distribution[thread_index].append(file)
        else:
            # 파일 개수가 스레드 개수보다 적은 경우: 각 파일을 여러 스레드에 복제
            files_per_thread = thread_count // len(files)
            remaining_threads = thread_count % len(files)
            
            thread_index = 0
            for file_idx, file in enumerate(files):
                assign_count = files_per_thread
                if file_idx < remaining_threads:
                    assign_count += 1
                
                for _ in range(assign_count):
                    if thread_index < thread_count:
                        distribution[thread_index].append(file)
                        thread_index += 1
            
            # 남은 스레드가 있다면 첫 번째 파일로 채움
            while thread_index < thread_count:
                distribution[thread_index].append(files[0])
                thread_index += 1
        
        return distribution
    
    def setup_ui(self):
        """UI 구성"""
        # 메인 프레임
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 제목
        title_label = ttk.Label(main_frame, text="🎥 고급 RTSP 영상 송출 프로그램", font=("TkDefaultFont", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=4, pady=(0, 20))
        
        # 전체 설정 프레임
        global_settings_frame = ttk.LabelFrame(main_frame, text="🌐 전체 설정", padding="10")
        global_settings_frame.grid(row=1, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # 네트워크 설정
        network_section = ttk.Frame(global_settings_frame)
        network_section.grid(row=0, column=0, columnspan=6, sticky=(tk.W, tk.E), pady=(0, 10))
        
        ttk.Label(network_section, text="🌐 서버 IP:", font=("TkDefaultFont", 10, "bold")).pack(side=tk.LEFT)
        
        self.server_ip_var = tk.StringVar(value=self.current_ip)
        ip_combo = ttk.Combobox(network_section, textvariable=self.server_ip_var, 
                               values=self.available_ips, width=15, state="readonly")
        ip_combo.pack(side=tk.LEFT, padx=(5, 10))
        
        ttk.Button(network_section, text="🔄 IP 새로고침", command=self.refresh_network_info).pack(side=tk.LEFT, padx=(0, 10))
        
        self.current_ip_label = ttk.Label(network_section, text=f"현재: {self.current_ip}", 
                                         font=("TkDefaultFont", 9), foreground="green")
        self.current_ip_label.pack(side=tk.LEFT, padx=(10, 0))
        
        self.server_ip_var.trace('w', self.update_all_rtsp_urls)
        
        # 파일 선택 섹션
        file_section = ttk.Frame(global_settings_frame)
        file_section.grid(row=1, column=0, columnspan=6, sticky=(tk.W, tk.E), pady=(0, 10))
        
        ttk.Button(file_section, text="📁 비디오 파일들 선택", command=self.browse_multiple_files).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(file_section, text="🗑️ 파일 목록 지우기", command=self.clear_input_files).pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Label(file_section, text="스레드 수:").pack(side=tk.LEFT, padx=(10, 0))
        self.thread_count_var = tk.IntVar(value=1)
        thread_spin = ttk.Spinbox(file_section, from_=1, to=6, textvariable=self.thread_count_var, width=8)
        thread_spin.pack(side=tk.LEFT, padx=(5, 10))
        
        ttk.Button(file_section, text="🔄 파일 분배", command=self.distribute_files).pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Label(file_section, text="기본 스트리밍:").pack(side=tk.LEFT, padx=(20, 0))
        self.global_stream_type = tk.StringVar(value="udp")
        stream_type_combo = ttk.Combobox(file_section, textvariable=self.global_stream_type,
                                        values=["udp", "rtsp"], width=8, state="readonly")
        stream_type_combo.pack(side=tk.LEFT, padx=(5, 0))
        
        # 파일 목록 표시
        files_display_section = ttk.Frame(global_settings_frame)
        files_display_section.grid(row=2, column=0, columnspan=6, sticky=(tk.W, tk.E), pady=(0, 10))
        
        ttk.Label(files_display_section, text="입력 파일 목록:", font=("TkDefaultFont", 10, "bold")).pack(anchor=tk.W)
        
        files_frame = ttk.Frame(files_display_section)
        files_frame.pack(fill=tk.BOTH, expand=True)
        
        self.files_listbox = tk.Listbox(files_frame, height=4, font=("TkDefaultFont", 9))
        scrollbar = ttk.Scrollbar(files_frame, orient="vertical", command=self.files_listbox.yview)
        self.files_listbox.configure(yscrollcommand=scrollbar.set)
        
        self.files_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 분배 결과 표시
        distribution_section = ttk.Frame(global_settings_frame)
        distribution_section.grid(row=3, column=0, columnspan=6, sticky=(tk.W, tk.E), pady=(0, 10))
        
        ttk.Label(distribution_section, text="파일 분배 결과:", font=("TkDefaultFont", 10, "bold")).pack(anchor=tk.W)
        self.distribution_label = ttk.Label(distribution_section, text="파일을 선택하고 분배 버튼을 클릭하세요.", 
                                          font=("TkDefaultFont", 9), foreground="gray")
        self.distribution_label.pack(anchor=tk.W, pady=(5, 0))
        
        # 전체 스트림 설정 섹션
        settings_section = ttk.Frame(global_settings_frame)
        settings_section.grid(row=4, column=0, columnspan=6, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # 전체 설정들
        ttk.Label(settings_section, text="전체 FPS:").grid(row=0, column=0, sticky=tk.W)
        self.global_fps_var = tk.IntVar(value=15)
        global_fps_spin = ttk.Spinbox(settings_section, from_=1, to=60, textvariable=self.global_fps_var, width=10)
        global_fps_spin.grid(row=0, column=1, sticky=tk.W, padx=(5, 15))
        
        ttk.Label(settings_section, text="전체 해상도:").grid(row=0, column=2, sticky=tk.W)
        self.global_resolution_var = tk.StringVar(value="1920x1080")
        global_resolution_combo = ttk.Combobox(settings_section, textvariable=self.global_resolution_var,
                                             values=["1920x1080", "1280x720", "640x480"], width=12, state="readonly")
        global_resolution_combo.grid(row=0, column=3, sticky=tk.W, padx=(5, 15))
        
        ttk.Label(settings_section, text="전체 비트레이트:").grid(row=0, column=4, sticky=tk.W)
        self.global_bitrate_var = tk.StringVar(value="2M")
        global_bitrate_combo = ttk.Combobox(settings_section, textvariable=self.global_bitrate_var,
                                           values=["500K", "1M", "2M", "4M", "8M"], width=10, state="readonly")
        global_bitrate_combo.grid(row=0, column=5, sticky=tk.W, padx=(5, 0))
        
        # 전체 설정 적용 버튼
        apply_section = ttk.Frame(global_settings_frame)
        apply_section.grid(row=5, column=0, columnspan=6, sticky=(tk.W, tk.E), pady=(0, 10))
        
        ttk.Button(apply_section, text="🔢 포트 자동 할당", command=self.auto_assign_ports).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(apply_section, text="⚙️ 전체 설정 적용", command=self.apply_global_settings).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(apply_section, text="✅ 활성 스트림 활성화", command=self.enable_active_streams).pack(side=tk.LEFT, padx=(0, 10))
        
        # 전체 제어 버튼
        control_frame = ttk.Frame(main_frame)
        control_frame.grid(row=2, column=0, columnspan=4, pady=(0, 15))
        
        # 큰 버튼 스타일
        style = ttk.Style()
        style.configure("Large.TButton", font=("TkDefaultFont", 12, "bold"))
        
        self.start_all_btn = ttk.Button(control_frame, text="🚀 전체 시작", command=self.start_all_streams, style="Large.TButton")
        self.start_all_btn.pack(side=tk.LEFT, padx=(0, 10), ipadx=10, ipady=5)
        
        self.stop_all_btn = ttk.Button(control_frame, text="⏹️ 전체 중지", command=self.stop_all_streams, style="Large.TButton")
        self.stop_all_btn.pack(side=tk.LEFT, padx=(0, 10), ipadx=10, ipady=5)
        
        ttk.Separator(control_frame, orient='vertical').pack(side=tk.LEFT, fill='y', padx=10)
        
        ttk.Button(control_frame, text="💾 설정 저장", command=self.save_settings).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(control_frame, text="📁 설정 불러오기", command=self.load_settings).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(control_frame, text="🔧 시스템 확인", command=self.check_system_status).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(control_frame, text="🌐 MediaMTX 설정", command=self.create_mediamtx_config).pack(side=tk.LEFT, padx=(0, 5))
        
        # 스트림별 설정 프레임들
        streams_container = ttk.Frame(main_frame)
        streams_container.grid(row=3, column=0, columnspan=4, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        
        for i in range(6):
            self.create_stream_frame(streams_container, i)
        
        # 전체 상태 정보
        status_frame = ttk.LabelFrame(main_frame, text="📊 전체 상태", padding="10")
        status_frame.grid(row=4, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=(10, 0))
        
        self.overall_status_label = ttk.Label(status_frame, text="대기 중...")
        self.overall_status_label.pack()
        
        # 사용법 안내
        help_frame = ttk.LabelFrame(main_frame, text="💡 RTSP 사용법", padding="10")
        help_frame.grid(row=5, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=(10, 0))
        
        help_text = """RTSP 사용법:
📱 로컬: rtsp://127.0.0.1:8554/live (같은 컴퓨터)
🌐 네트워크: rtsp://실제IP:8554/live (다른 장치에서)  
• 설정: '🌐 MediaMTX 설정' → start_all_mediamtx.bat 실행
• 각 포트별로 독립적인 MediaMTX 서버 실행"""
        
        ttk.Label(help_frame, text=help_text, font=("TkDefaultFont", 9), foreground="blue").pack(anchor=tk.W)
        
        # 그리드 가중치 설정
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(3, weight=1)
    
    def browse_multiple_files(self):
        """다중 비디오 파일 선택"""
        filetypes = [
            ("비디오 파일", "*.mp4 *.avi *.mov *.mkv *.wmv *.flv *.webm"),
            ("모든 파일", "*.*")
        ]
        
        filenames = filedialog.askopenfilenames(
            title="비디오 파일들 선택 (여러 개 선택 가능)",
            filetypes=filetypes
        )
        
        if filenames:
            self.input_files = list(filenames)
            self.update_files_display()
            self.distribute_files()
            
            message = f"{len(filenames)}개 파일이 선택되었습니다."
            messagebox.showinfo("파일 선택 완료", message)
            logger.info(f"다중 파일 선택: {len(filenames)}개 파일")
    
    def clear_input_files(self):
        """입력 파일 목록 지우기"""
        self.input_files = []
        self.update_files_display()
        self.clear_all_streams()
        self.distribution_label.config(text="파일을 선택하고 분배 버튼을 클릭하세요.")
        messagebox.showinfo("완료", "파일 목록이 지워졌습니다.")
    
    def update_files_display(self):
        """파일 목록 표시 업데이트"""
        self.files_listbox.delete(0, tk.END)
        for i, file_path in enumerate(self.input_files):
            filename = os.path.basename(file_path)
            self.files_listbox.insert(tk.END, f"{i+1}. {filename}")
    
    def distribute_files(self):
        """파일을 스레드 수에 따라 분배"""
        if not self.input_files:
            messagebox.showwarning("경고", "먼저 비디오 파일들을 선택해주세요.")
            return
        
        thread_count = self.thread_count_var.get()
        if thread_count <= 0 or thread_count > 6:
            messagebox.showerror("오류", "스레드 수는 1~6 사이여야 합니다.")
            return
        
        # 파일 분배
        distribution = self.distribute_files_to_threads(self.input_files, thread_count)
        
        # 모든 스트림 초기화
        self.clear_all_streams()
        
        # 분배 결과를 각 스트림에 적용
        distribution_text = "분배 결과: "
        active_streams = 0
        
        for i in range(thread_count):
            if i < len(distribution) and distribution[i]:
                self.file_vars[i].set(distribution[i][0])
                self.enable_vars[i].set(True)
                self.stream_type_vars[i].set(self.global_stream_type.get())
                
                # 스트림 설정에 여러 파일 목록 저장
                self.stream_configs[i].video_files = distribution[i]
                
                # 분배 정보 표시
                file_count = len(distribution[i])
                if file_count == 1:
                    file_name = os.path.basename(distribution[i][0])
                    display_text = f"📹 {file_name}"
                else:
                    file_list = [os.path.basename(f) for f in distribution[i]]
                    if len(set(file_list)) == 1:
                        display_text = f"📹 {file_list[0]} (복제)"
                    else:
                        display_text = f"🔄 {file_count}개 파일 순환: {', '.join(file_list[:2])}{' 외 ' + str(file_count-2) + '개' if file_count > 2 else ''}"
                
                getattr(self, f'thread_info_label_{i}').config(text=display_text)
                
                if active_streams > 0:
                    distribution_text += ", "
                distribution_text += f"스트림{i+1}({file_count}개)"
                active_streams += 1
                
                logger.info(f"스트림 {i+1}에 {file_count}개 파일 분배: {[os.path.basename(f) for f in distribution[i]]}")
        
        # 사용되지 않는 스트림들 비활성화
        for i in range(thread_count, 6):
            self.file_vars[i].set("")
            self.enable_vars[i].set(False)
            getattr(self, f'thread_info_label_{i}').config(text="")
        
        # 포트 자동 할당
        self.auto_assign_ports()
        
        # 전체 설정 적용
        self.apply_global_settings()
        
        # URL 업데이트
        self.update_all_rtsp_urls()
        
        # 분배 결과 표시
        self.distribution_label.config(text=distribution_text)
        
        # 성공 메시지
        total_files = len(self.input_files)
        success_message = f"파일 분배 완료:\n"
        
        if total_files >= thread_count:
            success_message += f"총 {total_files}개 파일을 {thread_count}개 스레드에 순환 분배\n\n"
        else:
            success_message += f"파일 {total_files}개를 {thread_count}개 스레드에 복제 분배\n"
            success_message += f"(각 파일이 여러 스트림에서 동시 송출)\n\n"
        
        for i in range(thread_count):
            if i < len(distribution) and distribution[i]:
                file_names = [os.path.basename(f) for f in distribution[i]]
                if len(set(file_names)) == 1:
                    success_message += f"스트림 {i+1}: {file_names[0]} (포트: {8554+i})\n"
                    success_message += f"  └ URL: rtsp://127.0.0.1:{8554+i}/live\n"
                else:
                    success_message += f"스트림 {i+1}: {len(distribution[i])}개 파일 (포트: {8554+i})\n"
                    success_message += f"  └ {', '.join(file_names[:2])}" 
                    if len(file_names) > 2:
                        success_message += f" 외 {len(file_names)-2}개"
                    success_message += f"\n  └ URL: rtsp://127.0.0.1:{8554+i}/live\n"
        
        success_message += f"\n✅ {active_streams}개 스트림이 활성화되었습니다."
        success_message += f"\n💡 '🚀 전체 시작' 버튼을 클릭하여 모든 스트림을 시작하세요."
        
        messagebox.showinfo("분배 완료", success_message)
        logger.info(f"파일 분배 완료: {total_files}개 파일을 {thread_count}개 스레드에 분배")
        
        # UI 업데이트 강제 적용
        self.root.update_idletasks()
    
    def clear_all_streams(self):
        """모든 스트림 설정 지우기"""
        for i in range(6):
            self.file_vars[i].set("")
            self.enable_vars[i].set(False)
            getattr(self, f'thread_info_label_{i}').config(text="")
    
    def create_stream_frame(self, parent, stream_id):
        """스트림별 설정 프레임 생성"""
        # 메인 프레임
        frame = ttk.LabelFrame(parent, text=f"📺 스트림 {stream_id + 1}", padding="10")
        frame.grid(row=stream_id // 2, column=stream_id % 2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        
        # 활성화 체크박스 및 스레드 정보
        header_frame = ttk.Frame(frame)
        header_frame.grid(row=0, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=(0, 5))
        
        enable_var = tk.BooleanVar()
        enable_check = ttk.Checkbutton(header_frame, text="활성화", variable=enable_var)
        enable_check.pack(side=tk.LEFT)
        
        # 스트림 타입 선택
        ttk.Label(header_frame, text="타입:").pack(side=tk.LEFT, padx=(10, 0))
        stream_type_var = tk.StringVar(value="udp")
        stream_type_combo = ttk.Combobox(header_frame, textvariable=stream_type_var,
                                        values=["udp", "rtsp"], width=8, state="readonly")
        stream_type_combo.pack(side=tk.LEFT, padx=(5, 10))
        
        # 스레드 정보 라벨
        thread_info_label = ttk.Label(header_frame, text="", font=("TkDefaultFont", 8), foreground="blue")
        thread_info_label.pack(side=tk.LEFT, padx=(10, 0))
        setattr(self, f'thread_info_label_{stream_id}', thread_info_label)
        
        self.enable_vars.append(enable_var)
        self.stream_type_vars.append(stream_type_var)
        
        # 비디오 파일 표시
        ttk.Label(frame, text="비디오 파일:").grid(row=1, column=0, sticky=tk.W)
        file_var = tk.StringVar()
        file_entry = ttk.Entry(frame, textvariable=file_var, width=60, state="readonly")
        file_entry.grid(row=1, column=1, columnspan=3, sticky=(tk.W, tk.E), padx=(5, 0))
        self.file_vars.append(file_var)
        
        # 포트 및 URL
        rtsp_frame = ttk.Frame(frame)
        rtsp_frame.grid(row=2, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=(5, 0))
        
        ttk.Label(rtsp_frame, text="포트:").grid(row=0, column=0, sticky=tk.W)
        port_var = tk.IntVar(value=8554 + stream_id)
        port_spin = ttk.Spinbox(rtsp_frame, from_=1024, to=65535, textvariable=port_var, width=10)
        port_spin.grid(row=0, column=1, sticky=tk.W, padx=(5, 15))
        
        ttk.Label(rtsp_frame, text="연결 URL:").grid(row=0, column=2, sticky=tk.W)
        rtsp_var = tk.StringVar(value=f"udp://@{self.current_ip}:{8554 + stream_id}")
        rtsp_entry = ttk.Entry(rtsp_frame, textvariable=rtsp_var, width=45, state="readonly")
        rtsp_entry.grid(row=0, column=3, sticky=(tk.W, tk.E), padx=(5, 0))
        
        self.rtsp_vars.append(rtsp_var)
        setattr(self, f'port_var_{stream_id}', port_var)
        
        # 포트나 스트림 타입 변경 시 URL 자동 업데이트
        def update_connection_url(*args):
            port = port_var.get()
            server_ip = self.server_ip_var.get()
            stream_type = stream_type_var.get()
            
            if stream_type == "rtsp":
                url = f"rtsp://{server_ip}:{port}/live"
            else:  # udp
                url = f"udp://@{server_ip}:{port}"
            
            rtsp_var.set(url)
        
        port_var.trace('w', update_connection_url)
        stream_type_var.trace('w', update_connection_url)
        
        # 개별 설정 옵션들
        settings_frame = ttk.Frame(frame)
        settings_frame.grid(row=3, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=(10, 0))
        
        # FPS
        ttk.Label(settings_frame, text="FPS:").grid(row=0, column=0, sticky=tk.W)
        fps_var = tk.IntVar(value=15)
        fps_spin = ttk.Spinbox(settings_frame, from_=1, to=60, textvariable=fps_var, width=8)
        fps_spin.grid(row=0, column=1, sticky=tk.W, padx=(5, 15))
        
        # 해상도
        ttk.Label(settings_frame, text="해상도:").grid(row=0, column=2, sticky=tk.W)
        resolution_var = tk.StringVar(value="1920x1080")
        resolution_combo = ttk.Combobox(settings_frame, textvariable=resolution_var, 
                                       values=["1920x1080", "1280x720", "640x480"], width=12, state="readonly")
        resolution_combo.grid(row=0, column=3, sticky=tk.W, padx=(5, 15))
        
        # 비트레이트
        ttk.Label(settings_frame, text="비트레이트:").grid(row=0, column=4, sticky=tk.W)
        bitrate_var = tk.StringVar(value="2M")
        bitrate_combo = ttk.Combobox(settings_frame, textvariable=bitrate_var,
                                    values=["500K", "1M", "2M", "4M", "8M"], width=8, state="readonly")
        bitrate_combo.grid(row=0, column=5, sticky=tk.W, padx=(5, 0))
        
        # 제어 버튼들
        button_frame = ttk.Frame(frame)
        button_frame.grid(row=4, column=0, columnspan=4, pady=(10, 0))
        
        start_btn = ttk.Button(button_frame, text="▶️ 시작", command=lambda i=stream_id: self.start_stream(i))
        start_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        stop_btn = ttk.Button(button_frame, text="⏹️ 중지", command=lambda i=stream_id: self.stop_stream(i))
        stop_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        # 테스트 버튼
        test_btn = ttk.Button(button_frame, text="🔍 VLC 테스트", command=lambda i=stream_id: self.test_vlc_connection(i))
        test_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        # 상태 표시
        status_label = ttk.Label(frame, text="대기 중", foreground="gray")
        status_label.grid(row=5, column=0, columnspan=4, pady=(10, 0))
        self.status_labels.append(status_label)
        
        # 설정 변수들 저장
        setattr(self, f'fps_var_{stream_id}', fps_var)
        setattr(self, f'resolution_var_{stream_id}', resolution_var)
        setattr(self, f'bitrate_var_{stream_id}', bitrate_var)
        
        self.stream_frames.append(frame)
        
        # 그리드 가중치
        frame.columnconfigure(1, weight=1)
        rtsp_frame.columnconfigure(3, weight=1)
        settings_frame.columnconfigure(1, weight=1)
        settings_frame.columnconfigure(3, weight=1)
        settings_frame.columnconfigure(5, weight=1)
    
    def test_vlc_connection(self, stream_id):
        """VLC로 연결 테스트"""
        connection_url = self.rtsp_vars[stream_id].get()
        
        try:
            subprocess.Popen(['vlc', connection_url], 
                           stdout=subprocess.DEVNULL, 
                           stderr=subprocess.DEVNULL)
            messagebox.showinfo("VLC 테스트", f"VLC가 실행되었습니다.\n연결 URL: {connection_url}")
        except FileNotFoundError:
            self.root.clipboard_clear()
            self.root.clipboard_append(connection_url)
            messagebox.showinfo("VLC 테스트", 
                               f"VLC가 설치되지 않았습니다.\n"
                               f"연결 URL이 클립보드에 복사되었습니다:\n{connection_url}\n\n"
                               f"VLC에서 수동으로 다음 단계를 따르세요:\n"
                               f"1. VLC 실행\n"
                               f"2. 미디어 > 네트워크 스트림 열기\n"
                               f"3. URL 붙여넣기")
    
    def auto_assign_ports(self):
        """포트 자동 할당"""
        base_port = 8554
        for i in range(6):
            port_var = getattr(self, f'port_var_{i}')
            port_var.set(base_port + i)
        
        logger.info(f"포트 자동 할당: {base_port}-{base_port+5}")
    
    def refresh_network_info(self):
        """네트워크 정보 새로고침"""
        old_ip = self.current_ip
        self.current_ip = get_local_ip()
        self.available_ips = get_all_network_interfaces()
        
        # IP 콤보박스 업데이트
        for widget in self.root.winfo_children():
            if isinstance(widget, ttk.Frame):
                for child in widget.winfo_children():
                    if isinstance(child, ttk.LabelFrame) and "전체 설정" in child.cget("text"):
                        for network_frame in child.winfo_children():
                            if isinstance(network_frame, ttk.Frame):
                                for widget_in_frame in network_frame.winfo_children():
                                    if isinstance(widget_in_frame, ttk.Combobox):
                                        widget_in_frame.configure(values=self.available_ips)
                                        break
                                break
                        break
                break
        
        if old_ip != self.current_ip:
            self.server_ip_var.set(self.current_ip)
        
        self.current_ip_label.config(text=f"현재: {self.current_ip}")
        
        messagebox.showinfo("네트워크 새로고침", 
                           f"네트워크 정보가 업데이트되었습니다.\n"
                           f"감지된 IP: {', '.join(self.available_ips)}\n"
                           f"현재 선택: {self.server_ip_var.get()}")
        
        logger.info(f"네트워크 정보 새로고침: {self.available_ips}")
    
    def update_all_rtsp_urls(self, *args):
        """모든 RTSP URL 업데이트"""
        server_ip = self.server_ip_var.get()
        for i in range(6):
            port = getattr(self, f'port_var_{i}').get()
            stream_type = self.stream_type_vars[i].get()
            
            if stream_type == "rtsp":
                url = f"rtsp://{server_ip}:{port}/live"
            else:  # udp
                url = f"udp://@{server_ip}:{port}"
            
            self.rtsp_vars[i].set(url)
        
        self.current_ip_label.config(text=f"현재: {server_ip}")
        logger.info(f"모든 스트림 URL을 {server_ip}로 업데이트")
    
    def apply_global_settings(self):
        """전체 설정을 활성화된 스트림에 적용"""
        global_fps = self.global_fps_var.get()
        global_resolution = self.global_resolution_var.get()
        global_bitrate = self.global_bitrate_var.get()
        
        applied_count = 0
        
        for i in range(6):
            if self.enable_vars[i].get():
                getattr(self, f'fps_var_{i}').set(global_fps)
                getattr(self, f'resolution_var_{i}').set(global_resolution)
                getattr(self, f'bitrate_var_{i}').set(global_bitrate)
                applied_count += 1
        
        if applied_count > 0:
            logger.info(f"전체 설정 적용: {applied_count}개 스트림에 FPS={global_fps}, 해상도={global_resolution}, 비트레이트={global_bitrate}")
    
    def enable_active_streams(self):
        """파일이 있는 스트림들 활성화"""
        enabled_count = 0
        for i in range(6):
            if self.file_vars[i].get():
                self.enable_vars[i].set(True)
                enabled_count += 1
        
        if enabled_count > 0:
            messagebox.showinfo("완료", f"{enabled_count}개 스트림이 활성화되었습니다.")
        else:
            messagebox.showwarning("경고", "활성화할 수 있는 스트림이 없습니다.\n파일을 먼저 선택해주세요.")
        logger.info(f"{enabled_count}개 스트림 활성화")
    
    def get_stream_config(self, stream_id):
        """스트림 설정 가져오기"""
        config = RTSPStreamConfig()
        config.video_file = self.file_vars[stream_id].get()
        
        # 순환 파일 목록 확인 및 설정
        if hasattr(self.stream_configs[stream_id], 'video_files') and self.stream_configs[stream_id].video_files:
            config.video_files = self.stream_configs[stream_id].video_files
            logger.info(f"스트림 {stream_id+1} 순환 파일 목록: {len(config.video_files)}개 파일")
        else:
            config.video_files = [config.video_file] if config.video_file else []
            logger.info(f"스트림 {stream_id+1} 단일 파일 모드")
        
        config.rtsp_url = self.rtsp_vars[stream_id].get()
        config.rtsp_port = getattr(self, f'port_var_{stream_id}').get()
        config.enabled = self.enable_vars[stream_id].get()
        config.stream_type = self.stream_type_vars[stream_id].get()
        
        config.fps = getattr(self, f'fps_var_{stream_id}').get()
        config.bitrate = getattr(self, f'bitrate_var_{stream_id}').get()
        
        resolution = getattr(self, f'resolution_var_{stream_id}').get()
        if 'x' in resolution:
            config.width, config.height = map(int, resolution.split('x'))
        
        return config
    
    def start_stream(self, stream_id):
        """개별 스트림 시작"""
        if stream_id in self.processes and self.processes[stream_id].is_alive():
            messagebox.showwarning("경고", f"스트림 {stream_id + 1}이 이미 실행 중입니다.")
            return
        
        config = self.get_stream_config(stream_id)
        
        if not config.enabled:
            messagebox.showwarning("경고", f"스트림 {stream_id + 1}이 활성화되지 않았습니다.")
            return
        
        # 순환 파일 목록이 있는지 확인
        if config.video_files:
            logger.info(f"스트림 {stream_id + 1} 순환 파일 목록 ({len(config.video_files)}개):")
            for i, file_path in enumerate(config.video_files):
                logger.info(f"  {i+1}. {os.path.basename(file_path)}")
                if not os.path.exists(file_path):
                    messagebox.showerror("오류", f"파일이 존재하지 않습니다:\n{file_path}")
                    return
        elif config.video_file:
            if not os.path.exists(config.video_file):
                messagebox.showerror("오류", f"비디오 파일이 존재하지 않습니다:\n{config.video_file}")
                return
        else:
            messagebox.showerror("오류", f"스트림 {stream_id + 1}의 비디오 파일을 선택하세요.")
            return
        
        # 프로세스 시작
        stop_event = Event()
        status_queue = Queue()
        
        process = Process(
            target=rtsp_sender_process,
            args=(stream_id, config, status_queue, stop_event),
            name=f"RTSPSender_{stream_id}"
        )
        
        process.start()
        
        self.processes[stream_id] = process
        self.stop_events[stream_id] = stop_event
        self.status_queues[stream_id] = status_queue
        
        # 순환 파일 정보 표시
        file_info = f"{len(config.video_files)}개 파일 순환" if config.video_files else "단일 파일"
        self.status_labels[stream_id].config(text=f"🟡 시작 중... ({file_info})", foreground="orange")
        logger.info(f"스트림 {stream_id + 1} 시작: {config.rtsp_url} ({file_info})")
    
    def stop_stream(self, stream_id):
        """개별 스트림 중지"""
        if stream_id in self.stop_events:
            self.stop_events[stream_id].set()
        
        if stream_id in self.processes:
            process = self.processes[stream_id]
            if process.is_alive():
                try:
                    process.join(timeout=5)
                    if process.is_alive():
                        process.terminate()
                        process.join(timeout=2)
                    logger.info(f"스트림 {stream_id + 1} 중지됨")
                except Exception as e:
                    logger.error(f"스트림 {stream_id + 1} 중지 오류: {e}")
            
            # PID 정보 제거
            if stream_id in self.stream_pids:
                del self.stream_pids[stream_id]
            
            del self.processes[stream_id]
            del self.stop_events[stream_id]
            del self.status_queues[stream_id]
        
        self.status_labels[stream_id].config(text="⚫ 중지됨", foreground="gray")
    
    def start_all_streams(self):
        """모든 활성화된 스트림 시작"""
        # 실행 중인 스트림이 있는지 확인
        running_streams = [i for i in self.processes.keys() if self.processes[i].is_alive()]
        if running_streams:
            response = messagebox.askyesno("확인", 
                                         f"{len(running_streams)}개 스트림이 이미 실행 중입니다.\n"
                                         f"모든 스트림을 중지하고 다시 시작하시겠습니까?")
            if response:
                self.stop_all_streams()
                time.sleep(1)
            else:
                return
        
        # 활성화된 스트림 확인
        active_streams = [i for i in range(6) if self.enable_vars[i].get()]
        if not active_streams:
            messagebox.showwarning("경고", "활성화된 스트림이 없습니다.")
            return
        
        # 전체 설정 자동 적용
        self.apply_global_settings()
        
        # 시작 상태 업데이트
        self.start_all_btn.config(state='disabled', text="🔄 시작 중...")
        self.stop_all_btn.config(state='normal')
        
        started_count = 0
        failed_streams = []
        
        for i in active_streams:
            try:
                config = self.get_stream_config(i)
                
                if not config.video_file:
                    failed_streams.append(f"스트림 {i+1}: 파일 없음")
                    continue
                
                if not os.path.exists(config.video_file):
                    failed_streams.append(f"스트림 {i+1}: 파일 없음 ({os.path.basename(config.video_file)})")
                    continue
                
                self.start_stream(i)
                started_count += 1
                time.sleep(0.3)  # 순차 시작으로 부하 분산
                
                # UI 업데이트
                self.root.update()
                
            except Exception as e:
                logger.error(f"스트림 {i + 1} 시작 실패: {e}")
                failed_streams.append(f"스트림 {i+1}: {str(e)}")
        
        # 시작 완료 상태 업데이트
        self.start_all_btn.config(state='normal', text="🚀 전체 시작")
        
        # 결과 메시지
        if started_count > 0:
            message = f"✅ {started_count}개 스트림이 시작되었습니다."
            if failed_streams:
                message += f"\n\n❌ 실패한 스트림:\n" + "\n".join(failed_streams)
            messagebox.showinfo("시작 완료", message)
        else:
            message = "❌ 시작된 스트림이 없습니다.\n\n실패 원인:\n" + "\n".join(failed_streams)
            messagebox.showerror("시작 실패", message)
        
        logger.info(f"전체 시작 완료: {started_count}개 성공, {len(failed_streams)}개 실패")
    
    def stop_all_streams(self):
        """모든 스트림 중지"""
        if not self.processes:
            messagebox.showinfo("정보", "실행 중인 스트림이 없습니다.")
            return
        
        # 중지 상태 업데이트
        self.stop_all_btn.config(state='disabled', text="🔄 중지 중...")
        self.start_all_btn.config(state='disabled')
        
        stopped_count = 0
        running_streams = list(self.processes.keys())
        
        for stream_id in running_streams:
            try:
                self.stop_stream(stream_id)
                stopped_count += 1
                
                # UI 업데이트
                self.root.update()
                
            except Exception as e:
                logger.error(f"스트림 {stream_id + 1} 중지 실패: {e}")
        
        # 추가 대기 (모든 프로세스 정리 완료 대기)
        time.sleep(1)
        
        # 중지 완료 상태 업데이트
        self.stop_all_btn.config(state='normal', text="⏹️ 전체 중지")
        self.start_all_btn.config(state='normal')
        
        if stopped_count > 0:
            messagebox.showinfo("중지 완료", f"✅ {stopped_count}개 스트림이 중지되었습니다.")
        
        logger.info(f"전체 중지 완료: {stopped_count}개 스트림 중지")
    
    def create_mediamtx_config(self):
        """MediaMTX 설정 파일 생성 도우미 (포트별 개별 인스턴스)"""
        
        # 기존 설정 파일들 정리
        old_files = []
        for i in range(1, 7):
            old_file = f"mediamtx_stream{i}.yml"
            if os.path.exists(old_file):
                old_files.append(old_file)
        
        if old_files:
            response = messagebox.askyesno("기존 파일 정리", 
                                         f"기존 설정 파일 {len(old_files)}개를 발견했습니다.\n"
                                         f"새로운 설정으로 덮어쓰시겠습니까?\n\n"
                                         f"파일들: {', '.join(old_files)}")
            if not response:
                return None
        
        # 각 포트별로 개별 MediaMTX 설정 파일들 생성
        config_files = []
        base_ports = [8554, 8555, 8556, 8557, 8558, 8559]
        rtmp_ports = [1935, 1936, 1937, 1938, 1939, 1940]
        
        for i in range(6):
            rtsp_port = base_ports[i]
            rtmp_port = rtmp_ports[i]
            api_port = 9997 + i
            
            # 최소한의 검증된 설정만 사용 (TCP 전용으로 UDP 충돌 완전 회피)
            config_content = f"""# MediaMTX 설정 파일 - 스트림 {i+1} (TCP 전용)
# 포트 {rtsp_port} 전용 인스턴스

# API 설정
api: yes
apiAddress: 127.0.0.1:{api_port}

# RTSP 서버 설정 (TCP 전용 - UDP 포트 충돌 회피)
rtspAddress: :{rtsp_port}
rtspTransports: [tcp]

# RTMP 서버 설정  
rtmpAddress: :{rtmp_port}

# 모든 추가 서비스 비활성화
hls: no
webrtc: no
srt: no

# 로그 설정
logLevel: info
logDestinations: [stdout]

# 타임아웃 설정
readTimeout: 10s
writeTimeout: 10s

# 스트림 경로 설정
paths:
  live:
    source: publisher
    sourceOnDemand: no
"""
            
            config_path = f"mediamtx_stream{i+1}.yml"
            try:
                # 파일 쓰기 전에 기존 파일 삭제
                if os.path.exists(config_path):
                    os.remove(config_path)
                
                with open(config_path, 'w', encoding='utf-8') as f:
                    f.write(config_content)
                config_files.append(config_path)
                logger.info(f"새 MediaMTX 설정 파일 생성: {config_path}")
            except Exception as e:
                logger.error(f"설정 파일 생성 실패 {config_path}: {e}")
                messagebox.showerror("오류", f"설정 파일 생성 실패:\n{config_path}\n{e}")
                return None
        
        if config_files:
            # 배치 파일 생성 (모든 MediaMTX 인스턴스 실행)
            batch_content = "@echo off\n"
            batch_content += "title MediaMTX 다중 인스턴스 관리자\n"
            batch_content += "color 0A\n"
            batch_content += "echo ==========================================\n"
            batch_content += "echo    MediaMTX 다중 인스턴스 시작\n"
            batch_content += "echo ==========================================\n"
            batch_content += "echo.\n"
            
            # 기존 MediaMTX 프로세스 정리
            batch_content += "echo [INFO] 기존 MediaMTX 프로세스 정리 중...\n"
            batch_content += "taskkill /f /im mediamtx.exe 2>nul\n"
            batch_content += "timeout /t 3 /nobreak >nul\n"
            batch_content += "echo.\n"
            
            # MediaMTX 실행 파일 확인
            batch_content += "echo [INFO] MediaMTX 실행 파일 확인 중...\n"
            batch_content += "mediamtx.exe --version >nul 2>&1\n"
            batch_content += "if errorlevel 1 (\n"
            batch_content += "    echo ❌ 오류: MediaMTX.exe를 찾을 수 없습니다!\n"
            batch_content += "    echo    MediaMTX를 다운로드하고 PATH에 추가하거나\n"
            batch_content += "    echo    이 배치 파일과 같은 폴더에 넣어주세요.\n"
            batch_content += "    echo    다운로드: https://github.com/bluenviron/mediamtx/releases\n"
            batch_content += "    pause\n"
            batch_content += "    exit /b 1\n"
            batch_content += ")\n"
            batch_content += "echo ✅ MediaMTX 실행 파일을 찾았습니다.\n"
            batch_content += "echo.\n"
            
            # 설정 파일 확인
            batch_content += "echo [INFO] 설정 파일들 확인 중...\n"
            for i, config_file in enumerate(config_files):
                batch_content += f'if not exist "{config_file}" (\n'
                batch_content += f'    echo ❌ 설정 파일 {config_file}이 없습니다!\n'
                batch_content += f'    echo    Python 프로그램에서 "🌐 MediaMTX 설정"을 다시 실행하세요.\n'
                batch_content += f'    pause\n'
                batch_content += f'    exit /b 1\n'
                batch_content += f')\n'
            batch_content += "echo ✅ 모든 설정 파일을 확인했습니다.\n"
            batch_content += "echo.\n"
            
            for i, config_file in enumerate(config_files):
                batch_content += f'echo [%time%] 스트림 {i+1} 시작 중... (RTSP:{base_ports[i]}, RTMP:{rtmp_ports[i]})\n'
                batch_content += f'echo   설정 파일: {config_file}\n'
                batch_content += f'if not exist "{config_file}" (\n'
                batch_content += f'    echo   ❌ 오류: 설정 파일 {config_file}을 찾을 수 없습니다!\n'
                batch_content += f'    pause\n'
                batch_content += f'    exit /b 1\n'
                batch_content += f')\n'
                batch_content += f'start "MediaMTX-Stream{i+1}-Port{base_ports[i]}" cmd /c "mediamtx.exe {config_file} & pause"\n'
                batch_content += "timeout /t 3 /nobreak >nul\n"
            
            batch_content += "echo.\n"
            batch_content += "echo [INFO] MediaMTX 인스턴스들이 시작되기를 기다리는 중...\n"
            batch_content += "timeout /t 8 /nobreak >nul\n"
            batch_content += "echo.\n"
            batch_content += "echo [INFO] MediaMTX 프로세스 확인:\n"
            batch_content += "tasklist /fi \"imagename eq mediamtx.exe\" 2>nul | find /i \"mediamtx.exe\" >nul\n"
            batch_content += "if errorlevel 1 (\n"
            batch_content += "    echo ❌ MediaMTX 프로세스가 실행되지 않았습니다!\n"
            batch_content += "    echo    설정 파일에 오류가 있거나 포트가 이미 사용중일 수 있습니다.\n"
            batch_content += "    echo.\n"
            batch_content += ") else (\n"
            batch_content += "    for /f \"tokens=2\" %%i in ('tasklist /fi \"imagename eq mediamtx.exe\" ^| find /c \"mediamtx.exe\"') do echo ✅ MediaMTX 프로세스 %%i개가 실행 중입니다.\n"
            batch_content += ")\n"
            batch_content += "echo.\n"
            batch_content += "echo ==========================================\n"
            batch_content += "echo 모든 MediaMTX 인스턴스 시작 완료!\n"
            batch_content += "echo.\n"
            batch_content += "echo 포트 상태 확인 (핵심 포트만):\n"
            for i in range(6):
                batch_content += f'netstat -an | findstr ":{rtmp_ports[i]}" >nul\n'
                batch_content += f'if errorlevel 1 (\n'
                batch_content += f'    echo   ❌ RTMP:{rtmp_ports[i]} 비활성\n'
                batch_content += f') else (\n'
                batch_content += f'    echo   ✅ RTMP:{rtmp_ports[i]} 활성\n'
                batch_content += f')\n'
                batch_content += f'netstat -an | findstr ":{base_ports[i]}" >nul\n'
                batch_content += f'if errorlevel 1 (\n'
                batch_content += f'    echo   ❌ RTSP:{base_ports[i]} 비활성\n'
                batch_content += f') else (\n'
                batch_content += f'    echo   ✅ RTSP:{base_ports[i]} 활성\n'
                batch_content += f')\n'
            
            batch_content += "echo.\n"
            batch_content += "echo 연결 URL:\n"
            batch_content += "echo.\n"
            batch_content += "echo 📱 로컬 연결 (같은 컴퓨터):\n"
            for i in range(6):
                batch_content += f'echo   스트림 {i+1}: rtsp://127.0.0.1:{base_ports[i]}/live\n'
            batch_content += "echo.\n"
            batch_content += f'echo 🌐 네트워크 연결 (다른 장치에서):\n'
            for i in range(6):
                batch_content += f'echo   스트림 {i+1}: rtsp://{self.server_ip_var.get()}:{base_ports[i]}/live\n'
            batch_content += "echo.\n"
            batch_content += "echo ⚠️ 비활성 포트가 있다면 다음을 확인하세요:\n"
            batch_content += "echo 1. MediaMTX.exe가 PATH에 있는지 확인\n"
            batch_content += "echo 2. 방화벽에서 포트가 허용되어 있는지 확인\n"
            batch_content += "echo 3. 다른 프로그램이 포트를 사용하고 있지 않은지 확인\n"
            batch_content += "echo.\n"
            batch_content += "echo 종료하려면 모든 MediaMTX 창을 닫거나\n"
            batch_content += "echo stop_all_mediamtx.bat을 실행하세요.\n"
            batch_content += "echo ==========================================\n"
            batch_content += "echo.\n"
            batch_content += "echo Python 프로그램에서 '🚀 전체 시작' 버튼을 눌러\n"
            batch_content += "echo 스트리밍을 시작하세요!\n"
            batch_content += "pause\n"
            
            # 종료 배치 파일도 생성
            stop_batch_content = "@echo off\n"
            stop_batch_content += "echo MediaMTX 인스턴스들을 종료합니다...\n"
            stop_batch_content += "tasklist | find /i \"mediamtx.exe\" >nul\n"
            stop_batch_content += "if errorlevel 1 (\n"
            stop_batch_content += "    echo MediaMTX 프로세스가 실행되지 않고 있습니다.\n"
            stop_batch_content += ") else (\n"
            stop_batch_content += "    taskkill /f /im mediamtx.exe 2>nul\n"
            stop_batch_content += "    echo 모든 MediaMTX 인스턴스가 종료되었습니다.\n"
            stop_batch_content += ")\n"
            stop_batch_content += "pause\n"
            
            # 단일 테스트용 배치 파일
            test_batch_content = "@echo off\n"
            test_batch_content += "title MediaMTX 단일 테스트\n"
            test_batch_content += "echo ==========================================\n"
            test_batch_content += "echo MediaMTX 단일 인스턴스 테스트 (포트 8554)\n"
            test_batch_content += "echo ==========================================\n"
            test_batch_content += "echo.\n"
            test_batch_content += "echo [INFO] 설정 파일 확인 중...\n"
            test_batch_content += "if not exist \"mediamtx_stream1.yml\" (\n"
            test_batch_content += "    echo ❌ mediamtx_stream1.yml 파일이 없습니다!\n"
            test_batch_content += "    pause\n"
            test_batch_content += "    exit /b 1\n"
            test_batch_content += ")\n"
            test_batch_content += "echo ✅ 설정 파일을 찾았습니다.\n"
            test_batch_content += "echo.\n"
            test_batch_content += "echo [INFO] MediaMTX 시작 중... (Ctrl+C로 종료)\n"
            test_batch_content += "echo 연결 URL: rtsp://127.0.0.1:8554/live\n"
            test_batch_content += "echo.\n"
            test_batch_content += "mediamtx.exe mediamtx_stream1.yml\n"
            test_batch_content += "echo.\n"
            test_batch_content += "echo MediaMTX가 종료되었습니다.\n"
            test_batch_content += "pause\n"
            
            # 최소 설정 파일도 생성 (UDP 포트 충돌 회피)  
            minimal_config = f"""# MediaMTX 절대 최소 설정 (UDP 충돌 해결)

# RTSP 서버 (TCP만 사용)
rtspAddress: :8554
rtspTransports: [tcp]

# RTMP 서버
rtmpAddress: :1935

# 모든 추가 기능 비활성화
hls: no
webrtc: no
srt: no

# 스트림 경로
paths:
  live:
    source: publisher
"""
            
            minimal_config_file = "mediamtx_minimal.yml"
            
            batch_file = "start_all_mediamtx.bat"
            stop_batch_file = "stop_all_mediamtx.bat"
            test_batch_file = "test_single_mediamtx.bat"
            
            try:
                with open(batch_file, 'w', encoding='utf-8') as f:
                    f.write(batch_content)
                
                with open(stop_batch_file, 'w', encoding='utf-8') as f:
                    f.write(stop_batch_content)
                    
                with open(test_batch_file, 'w', encoding='utf-8') as f:
                    f.write(test_batch_content)
                
                # 최소 설정 파일 생성 (기존 파일 삭제 후)
                if os.path.exists(minimal_config_file):
                    os.remove(minimal_config_file)
                with open(minimal_config_file, 'w', encoding='utf-8') as f:
                    f.write(minimal_config)
                
                # 최소 설정 테스트 배치 파일
                minimal_test_batch = "@echo off\n"
                minimal_test_batch += "title MediaMTX 최소 설정 테스트\n"
                minimal_test_batch += "echo ==========================================\n"
                minimal_test_batch += "echo MediaMTX 최소 설정 테스트 (포트 8554)\n"
                minimal_test_batch += "echo ==========================================\n"
                minimal_test_batch += "echo 연결 URL: rtsp://127.0.0.1:8554/live\n"
                minimal_test_batch += "echo.\n"
                minimal_test_batch += "echo [INFO] 기존 MediaMTX 프로세스 종료...\n"
                minimal_test_batch += "taskkill /f /im mediamtx.exe 2>nul\n"
                minimal_test_batch += "timeout /t 2 /nobreak >nul\n"
                minimal_test_batch += "echo.\n"
                minimal_test_batch += "echo [INFO] MediaMTX 시작 중... (Ctrl+C로 종료)\n"
                minimal_test_batch += "mediamtx.exe mediamtx_minimal.yml\n"
                minimal_test_batch += "echo.\n"
                minimal_test_batch += "echo MediaMTX가 종료되었습니다.\n"
                minimal_test_batch += "pause\n"
                
                minimal_test_file = "test_minimal_mediamtx.bat"
                if os.path.exists(minimal_test_file):
                    os.remove(minimal_test_file)
                with open(minimal_test_file, 'w', encoding='utf-8') as f:
                    f.write(minimal_test_batch)
                
                message = f"MediaMTX 설정 파일이 새로 생성되었습니다! (TCP 전용)\n\n"
                message += f"🗑️ 기존 파일 정리: {len(old_files)}개 파일 제거됨\n"
                message += f"🔧 UDP 포트 충돌 해결: TCP 전용 모드로 설정\n\n"
                message += f"📁 새로 생성된 파일들:\n"
                for i, config_file in enumerate(config_files):
                    message += f"• {config_file} (RTSP:{base_ports[i]} TCP전용, RTMP:{rtmp_ports[i]})\n"
                message += f"• {minimal_config_file} (절대 최소 설정 - TCP전용)\n"
                message += f"• {batch_file} (모든 인스턴스 시작)\n"
                message += f"• {stop_batch_file} (모든 인스턴스 종료)\n"
                message += f"• {test_batch_file} (단일 테스트용)\n"
                message += f"• {minimal_test_file} (최소 설정 테스트)\n\n"
                
                message += f"🚀 반드시 이 순서로 테스트하세요:\n"
                message += f"1. {minimal_test_file} → 기본 기능 확인 (TCP만)\n"
                message += f"2. {test_batch_file} → 개별 인스턴스 확인\n"
                message += f"3. {batch_file} → 전체 시스템 시작\n\n"
                
                message += f"🔧 주요 변경사항:\n"
                message += f"• ✅ TCP 전용 모드로 UDP 포트 충돌 완전 회피\n"
                message += f"• ✅ rtspTransports: [tcp] 설정으로 UDP 비활성화\n"
                message += f"• ✅ 각 인스턴스가 독립적인 RTSP/RTMP 포트만 사용\n"
                message += f"• ✅ 더 안정적이고 충돌 없는 스트리밍\n\n"
                
                message += f"📡 스트림 연결 URL (TCP 전용):\n"
                for i in range(6):
                    message += f"• 스트림 {i+1}: rtsp://{self.server_ip_var.get()}:{base_ports[i]}/live\n"
                
                message += f"\n💡 TCP 전용 모드로 UDP 포트 충돌이 완전히 해결되었습니다!\n"
                message += f"💡 TCP는 더 안정적이며 방화벽 설정도 간단합니다."
                
                messagebox.showinfo("다중 MediaMTX 설정 완료", message)
                
                return batch_file
                
            except Exception as e:
                messagebox.showerror("오류", f"배치 파일 생성 실패:\n{e}")
                return None
        else:
            messagebox.showerror("오류", "설정 파일 생성에 실패했습니다.")
            return None
    
    def check_system_status(self):
        """시스템 상태 확인"""
        ffmpeg_status = "✅ 정상" if check_ffmpeg() else "❌ 미설치"
        mediamtx_status = "✅ 설치됨" if check_mediamtx() else "❌ 미설치 (RTSP 필요)"
        
        # MediaMTX 상태 확인
        mediamtx_running = False
        active_streams = []
        try:
            import requests
            # MediaMTX API로 상태 확인
            response = requests.get("http://127.0.0.1:9997/v3/config/global/get", timeout=2)
            mediamtx_running = response.status_code == 200
            
            # 활성 스트림 확인
            if mediamtx_running:
                try:
                    streams_response = requests.get("http://127.0.0.1:9997/v3/paths/list", timeout=2)
                    if streams_response.status_code == 200:
                        streams_data = streams_response.json()
                        for path_name, path_info in streams_data.get('items', {}).items():
                            if path_info.get('source') == 'publisher' and path_info.get('ready', False):
                                active_streams.append(path_name)
                except:
                    pass
        except:
            pass
        
        mediamtx_runtime_status = "🟢 실행 중" if mediamtx_running else "🔴 중지됨"
        
        try:
            if check_ffmpeg():
                result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True, timeout=5)
                version_line = result.stdout.split('\n')[0]
                
                status_message = f"📋 시스템 상태 확인\n\n"
                status_message += f"FFmpeg: {ffmpeg_status}\n"
                status_message += f"└ {version_line}\n\n"
                status_message += f"MediaMTX: {mediamtx_status}\n"
                status_message += f"└ 서비스 상태: {mediamtx_runtime_status}\n"
                
                status_message += f"🔍 다중 MediaMTX 인스턴스 상태:\n"
                if mediamtx_running:
                    # 각 MediaMTX 인스턴스 상태 확인
                    running_instances = 0
                    for i in range(4):  # 주요 4개만 확인
                        try:
                            api_port = 9997 + i
                            rtsp_port = 8554 + i
                            rtmp_port = 1935 + i
                            
                            # 포트 연결 테스트
                            import socket
                            rtmp_alive = False
                            rtsp_alive = False
                            
                            try:
                                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                                    s.settimeout(1)
                                    rtmp_alive = (s.connect_ex(('127.0.0.1', rtmp_port)) == 0)
                            except:
                                pass
                                
                            try:
                                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                                    s.settimeout(1)
                                    rtsp_alive = (s.connect_ex(('127.0.0.1', rtsp_port)) == 0)
                            except:
                                pass
                            
                            if rtmp_alive and rtsp_alive:
                                status_message += f"  ✅ 인스턴스 {i+1} (RTSP:{rtsp_port}, RTMP:{rtmp_port}): 정상\n"
                                running_instances += 1
                            elif rtsp_alive:
                                status_message += f"  ⚠️ 인스턴스 {i+1} (RTSP:{rtsp_port}): RTMP 대기 중\n"
                            else:
                                status_message += f"  ❌ 인스턴스 {i+1}: 미실행\n"
                                
                        except Exception as e:
                            status_message += f"  ❌ 인스턴스 {i+1}: 상태 확인 실패\n"
                    
                    if running_instances == 0:
                        status_message += f"  ⚠️ start_all_mediamtx.bat을 실행하세요!\n"
                    else:
                        status_message += f"  💡 {running_instances}개 인스턴스 정상 실행 중\n"
                else:
                    status_message += f"  ❌ MediaMTX 인스턴스들이 실행되지 않았습니다.\n"
                    status_message += f"      start_all_mediamtx.bat을 먼저 실행하세요.\n"
                
                status_message += f"\n"
                
                status_message += f"\n🌐 네트워크 설정\n"
                status_message += f"현재 서버 IP: {self.server_ip_var.get()}\n"
                status_message += f"사용 가능한 IP: {', '.join(self.available_ips)}\n\n"
                
                status_message += f"💡 독립 MediaMTX 인스턴스 방식\n"
                status_message += f"각 스트림이 별도의 MediaMTX 인스턴스를 사용:\n"
                status_message += f"• rtsp://{self.server_ip_var.get()}:8554/live (스트림 1)\n"
                status_message += f"• rtsp://{self.server_ip_var.get()}:8555/live (스트림 2)\n"
                status_message += f"• rtsp://{self.server_ip_var.get()}:8556/live (스트림 3)\n"
                status_message += f"• rtsp://{self.server_ip_var.get()}:8557/live (스트림 4)\n\n"
                
                status_message += f"🔧 다중 MediaMTX 설정\n"
                status_message += f"1. '🌐 MediaMTX 설정' 버튼 클릭\n"
                status_message += f"2. start_all_mediamtx.bat 실행\n"
                status_message += f"3. 방화벽에서 포트 8554-8559, 1935-1940 허용\n\n"
                
                status_message += f"📋 VLC 테스트\n"
                status_message += f"각 스트림을 개별적으로 테스트하세요."
                
                messagebox.showinfo("시스템 상태", status_message)
            else:
                messagebox.showerror("시스템 상태", 
                                   f"❌ FFmpeg가 설치되지 않았습니다.\n\n" +
                                   f"설치 방법:\n" +
                                   f"1. Windows: https://ffmpeg.org/download.html\n" +
                                   f"2. macOS: brew install ffmpeg\n" +
                                   f"3. Ubuntu: sudo apt install ffmpeg\n\n" +
                                   f"MediaMTX: {mediamtx_status} ({mediamtx_runtime_status})")
        except Exception as e:
            messagebox.showerror("시스템 상태", f"상태 확인 중 오류 발생:\n{e}")
    
    def start_monitoring(self):
        """상태 모니터링 시작"""
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
        self.monitor_thread.start()
    
    def monitor_loop(self):
        """모니터링 루프"""
        while self.monitoring:
            try:
                # 각 스트림 상태 확인
                running_count = 0
                for stream_id in range(6):
                    if stream_id in self.status_queues:
                        try:
                            while True:
                                sid, status, message = self.status_queues[stream_id].get_nowait()
                                
                                if status == 'pid':
                                    # PID 정보 저장
                                    self.stream_pids[stream_id] = message
                                elif status == 'running':
                                    self.status_labels[stream_id].config(text=f"🟢 실행 중: {message}", foreground="green")
                                    running_count += 1
                                elif status == 'ready':
                                    self.status_labels[stream_id].config(text=f"🟢 준비됨: {message}", foreground="green")
                                    running_count += 1
                                elif status == 'error':
                                    self.status_labels[stream_id].config(text=f"🔴 오류: {message}", foreground="red")
                                elif status == 'stopped':
                                    self.status_labels[stream_id].config(text="⚫ 중지됨", foreground="gray")
                        except:
                            if stream_id in self.processes and self.processes[stream_id].is_alive():
                                running_count += 1
                
                # 전체 상태 업데이트
                if running_count > 0:
                    # 실행 중인 PID 목록
                    active_pids = [str(pid) for pid in self.stream_pids.values()]
                    pid_info = f"PID: {', '.join(active_pids)}" if active_pids else ""
                    
                    files_info = ""
                    if self.input_files:
                        files_info = f"📁 {len(self.input_files)}개 파일 처리 중"
                    
                    self.overall_status_label.config(
                        text=f"📡 {running_count}개 스트림 송출 중 - {files_info} - {pid_info} - {datetime.now().strftime('%H:%M:%S')}"
                    )
                else:
                    files_info = ""
                    if self.input_files:
                        files_info = f"📁 {len(self.input_files)}개 파일 준비됨 - "
                    
                    self.overall_status_label.config(text=f"⭕ 송출 중인 스트림 없음 - {files_info}대기 중")
                
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"모니터링 오류: {e}")
                time.sleep(5)
    
    def save_settings(self):
        """설정 저장"""
        settings = {
            'global_settings': {
                'fps': self.global_fps_var.get(),
                'resolution': self.global_resolution_var.get(),
                'bitrate': self.global_bitrate_var.get(),
                'thread_count': self.thread_count_var.get(),
                'server_ip': self.server_ip_var.get(),
                'stream_type': self.global_stream_type.get()
            },
            'input_files': self.input_files,
            'streams': []
        }
        
        for i in range(6):
            config = self.get_stream_config(i)
            stream_settings = {
                'enabled': config.enabled,
                'video_file': config.video_file,
                'rtsp_url': config.rtsp_url,
                'rtsp_port': config.rtsp_port,
                'fps': config.fps,
                'width': config.width,
                'height': config.height,
                'bitrate': config.bitrate,
                'stream_type': config.stream_type
            }
            settings['streams'].append(stream_settings)
        
        filename = filedialog.asksaveasfilename(
            title="설정 저장",
            defaultextension=".json",
            filetypes=[("JSON 파일", "*.json"), ("모든 파일", "*.*")]
        )
        
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(settings, f, indent=2, ensure_ascii=False)
                messagebox.showinfo("성공", f"설정이 저장되었습니다:\n{filename}")
            except Exception as e:
                messagebox.showerror("오류", f"설정 저장 실패:\n{e}")
    
    def load_settings(self):
        """설정 불러오기"""
        filename = filedialog.askopenfilename(
            title="설정 불러오기",
            filetypes=[("JSON 파일", "*.json"), ("모든 파일", "*.*")]
        )
        
        if filename:
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                
                # 전체 설정 불러오기
                global_settings = settings.get('global_settings', {})
                if global_settings:
                    self.global_fps_var.set(global_settings.get('fps', 15))
                    self.global_resolution_var.set(global_settings.get('resolution', '1920x1080'))
                    self.global_bitrate_var.set(global_settings.get('bitrate', '2M'))
                    self.thread_count_var.set(global_settings.get('thread_count', 1))
                    self.global_stream_type.set(global_settings.get('stream_type', 'udp'))
                    
                    # 서버 IP 설정 (있는 경우)
                    if 'server_ip' in global_settings:
                        saved_ip = global_settings['server_ip']
                        if saved_ip in self.available_ips:
                            self.server_ip_var.set(saved_ip)
                
                # 입력 파일 목록 불러오기
                self.input_files = settings.get('input_files', [])
                self.update_files_display()
                
                # 개별 스트림 설정 불러오기
                for i, stream_settings in enumerate(settings.get('streams', [])):
                    if i < 6:  # 최대 6개
                        self.enable_vars[i].set(stream_settings.get('enabled', False))
                        self.file_vars[i].set(stream_settings.get('video_file', ''))
                        self.stream_type_vars[i].set(stream_settings.get('stream_type', 'udp'))
                        
                        # 포트 설정
                        port = stream_settings.get('rtsp_port', 8554 + i)
                        getattr(self, f'port_var_{i}').set(port)
                        
                        # URL은 자동으로 업데이트됨 (trace 함수에 의해)
                        
                        getattr(self, f'fps_var_{i}').set(stream_settings.get('fps', 15))
                        getattr(self, f'bitrate_var_{i}').set(stream_settings.get('bitrate', '2M'))
                        
                        width = stream_settings.get('width', 1920)
                        height = stream_settings.get('height', 1080)
                        getattr(self, f'resolution_var_{i}').set(f'{width}x{height}')
                
                # 분배 다시 실행
                if self.input_files:
                    self.distribute_files()
                
                messagebox.showinfo("성공", f"설정이 불러와졌습니다:\n{filename}")
                
            except Exception as e:
                messagebox.showerror("오류", f"설정 불러오기 실패:\n{e}")
    
    def on_closing(self):
        """프로그램 종료 처리"""
        self.monitoring = False
        self.stop_all_streams()
        
        # 모든 프로세스 종료 대기
        for stream_id in list(self.processes.keys()):
            if self.processes[stream_id].is_alive():
                try:
                    self.processes[stream_id].terminate()
                    self.processes[stream_id].join(timeout=3)
                except:
                    pass
        
        self.root.destroy()

def main():
    """메인 함수"""
    # 멀티프로세싱 설정 (Windows 호환성)
    if hasattr(mp, 'set_start_method'):
        try:
            mp.set_start_method('spawn', force=True)
        except RuntimeError:
            pass
    
    root = tk.Tk()
    app = RTSPSenderGUI(root)
    
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()