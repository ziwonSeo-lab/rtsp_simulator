#!/usr/bin/env python3
"""
tc(Traffic Control) 기반 네트워크 시뮬레이션 RTSP 송출 프로그램

주요 기능:
- tc를 이용한 실제 네트워크 레벨 패킷 손실/지연/지터 시뮬레이션
- 가상 네트워크 인터페이스별 독립적인 네트워크 조건 적용
- 여러 영상 파일을 동시 송출
- MediaMTX 기반 RTSP 송출

요구사항:
- Linux tc 명령어 (iproute2 패키지)
- sudo 권한 (네트워크 설정 변경용)
- FFmpeg 설치
- MediaMTX 설치 (선택사항)
"""

import os
import sys
import subprocess
import time
import threading
import multiprocessing as mp
from multiprocessing import Process, Event, Queue, Manager
import logging
import json
import socket
import tempfile
import signal
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('rtsp_sender_tc.log')
    ]
)
logger = logging.getLogger(__name__)

class NetworkSimulator:
    """tc를 이용한 네트워크 시뮬레이션 클래스"""
    
    def __init__(self):
        self.active_interfaces = {}
        self.base_interface = self._get_default_interface()
        logger.info(f"기본 네트워크 인터페이스: {self.base_interface}")
    
    def _get_default_interface(self):
        """기본 네트워크 인터페이스 이름 가져오기"""
        try:
            # 기본 라우트의 인터페이스 찾기
            result = subprocess.run(['ip', 'route', 'show', 'default'], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'default' in line and 'dev' in line:
                        parts = line.split()
                        dev_index = parts.index('dev')
                        if dev_index + 1 < len(parts):
                            return parts[dev_index + 1]
            
            # 대체 방법: 주요 이더넷 인터페이스들 확인
            common_interfaces = ['eth0', 'eno1', 'enp0s3', 'wlan0']
            for iface in common_interfaces:
                result = subprocess.run(['ip', 'link', 'show', iface], 
                                      capture_output=True, text=True)
                if result.returncode == 0:
                    return iface
            
            return 'eth0'  # 기본값
        except Exception as e:
            logger.warning(f"기본 인터페이스 감지 실패: {e}")
            return 'eth0'
    
    def check_tc_support(self):
        """tc 명령어 지원 확인"""
        try:
            # tc 명령어 절대 경로로 확인 (help 옵션 사용)
            result = subprocess.run(['/usr/sbin/tc', '-help'], 
                                  capture_output=True, text=True)
            return result.returncode == 0
        except FileNotFoundError:
            # 절대 경로로 찾을 수 없는 경우 PATH에서 검색
            try:
                result = subprocess.run(['tc', '-help'], 
                                      capture_output=True, text=True)
                return result.returncode == 0
            except FileNotFoundError:
                return False
    
    def setup_virtual_interface(self, stream_id: int, target_ip: str, target_port: int):
        """가상 네트워크 인터페이스 설정"""
        veth_name = f"veth{stream_id}"
        peer_name = f"peer{stream_id}"
        
        try:
            # 기존 가상 인터페이스 제거
            self.cleanup_virtual_interface(stream_id)
            
            # veth pair 생성
            subprocess.run([
                'sudo', 'ip', 'link', 'add', veth_name, 
                'type', 'veth', 'peer', 'name', peer_name
            ], check=True)
            
            # 인터페이스 활성화
            subprocess.run(['sudo', 'ip', 'link', 'set', veth_name, 'up'], check=True)
            subprocess.run(['sudo', 'ip', 'link', 'set', peer_name, 'up'], check=True)
            
            # IP 주소 할당 (서브넷 분리)
            veth_ip = f"192.168.{100 + stream_id}.1/24"
            peer_ip = f"192.168.{100 + stream_id}.2/24"
            
            subprocess.run(['sudo', 'ip', 'addr', 'add', veth_ip, 'dev', veth_name], check=True)
            subprocess.run(['sudo', 'ip', 'addr', 'add', peer_ip, 'dev', peer_name], check=True)
            
            self.active_interfaces[stream_id] = {
                'veth': veth_name,
                'peer': peer_name,
                'veth_ip': veth_ip.split('/')[0],
                'peer_ip': peer_ip.split('/')[0]
            }
            
            logger.info(f"가상 인터페이스 생성: {veth_name} <-> {peer_name}")
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"가상 인터페이스 설정 실패: {e}")
            return False
    
    def apply_network_conditions(self, stream_id: int, packet_loss: float, 
                                delay: int, jitter: int, bandwidth_limit: int):
        """네트워크 조건 적용"""
        if stream_id not in self.active_interfaces:
            logger.error(f"스트림 {stream_id}의 가상 인터페이스가 없습니다.")
            return False
        
        interface_name = self.active_interfaces[stream_id]['veth']
        
        try:
            # 기존 qdisc 제거
            subprocess.run(['sudo', 'tc', 'qdisc', 'del', 'dev', interface_name, 'root'], 
                         capture_output=True)
            
            # netem qdisc로 네트워크 조건 설정
            netem_params = ['sudo', 'tc', 'qdisc', 'add', 'dev', interface_name, 'root', 'netem']
            
            # 패킷 손실
            if packet_loss > 0:
                netem_params.extend(['loss', f'{packet_loss}%'])
            
            # 지연
            if delay > 0:
                if jitter > 0:
                    netem_params.extend(['delay', f'{delay}ms', f'{jitter}ms'])
                else:
                    netem_params.extend(['delay', f'{delay}ms'])
            
            # 대역폭 제한 (tbf qdisc 사용)
            if bandwidth_limit > 0:
                # tbf를 root로 먼저 설정하고, netem을 child로 설정
                rate = f'{bandwidth_limit}mbit'
                burst = f'{max(bandwidth_limit * 1000, 32000)}'  # 최소 32KB
                
                # tbf qdisc를 root로 추가 (대역폭 제한)
                subprocess.run([
                    'sudo', 'tc', 'qdisc', 'add', 'dev', interface_name,
                    'root', 'handle', '1:', 'tbf',
                    'rate', rate, 'burst', burst, 'limit', str(burst * 2)
                ], check=True)
                
                # netem을 tbf의 child로 추가
                netem_child_params = ['sudo', 'tc', 'qdisc', 'add', 'dev', interface_name, 'parent', '1:1', 'netem']
                # 패킷 손실, 지연, 지터 설정만 추가
                if packet_loss > 0:
                    netem_child_params.extend(['loss', f'{packet_loss}%'])
                if delay > 0:
                    if jitter > 0:
                        netem_child_params.extend(['delay', f'{delay}ms', f'{jitter}ms'])
                    else:
                        netem_child_params.extend(['delay', f'{delay}ms'])
                
                subprocess.run(netem_child_params, check=True)
                
            else:
                # 대역폭 제한이 없는 경우 netem만 실행
                subprocess.run(netem_params, check=True)
            
            logger.info(f"스트림 {stream_id} 네트워크 조건 적용: "
                       f"손실={packet_loss}%, 지연={delay}ms, 지터={jitter}ms, "
                       f"대역폭={bandwidth_limit}Mbps")
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"네트워크 조건 적용 실패: {e}")
            return False
    
    def cleanup_virtual_interface(self, stream_id: int):
        """가상 인터페이스 정리"""
        veth_name = f"veth{stream_id}"
        peer_name = f"peer{stream_id}"
        
        try:
            # 기존 인터페이스가 있는지 확인하고 정리
            result = subprocess.run(['ip', 'link', 'show', veth_name], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                # qdisc 제거 (있는 경우에만)
                subprocess.run(['sudo', 'tc', 'qdisc', 'del', 'dev', veth_name, 'root'], 
                             capture_output=True)
                
                # 가상 인터페이스 제거 (veth pair는 한쪽만 제거하면 둘 다 제거됨)
                result = subprocess.run(['sudo', 'ip', 'link', 'del', veth_name], 
                                      capture_output=True)
                if result.returncode == 0:
                    logger.info(f"기존 가상 인터페이스 {veth_name} 정리 완료")
                else:
                    logger.warning(f"가상 인터페이스 {veth_name} 삭제 실패: {result.stderr.decode()}")
            
            # active_interfaces에서도 제거
            if stream_id in self.active_interfaces:
                del self.active_interfaces[stream_id]
                
        except Exception as e:
            logger.warning(f"가상 인터페이스 정리 중 오류: {e}")
    
    def cleanup_all_interfaces(self):
        """모든 가상 인터페이스 정리"""
        for stream_id in list(self.active_interfaces.keys()):
            self.cleanup_virtual_interface(stream_id)
    
    def get_interface_ip(self, stream_id: int):
        """가상 인터페이스 IP 주소 반환"""
        if stream_id in self.active_interfaces:
            return self.active_interfaces[stream_id]['peer_ip']
        return None

class RTSPStreamConfig:
    """RTSP 스트림 설정 클래스"""
    def __init__(self, config_dict: Dict[str, Any] = None):
        if config_dict is None:
            config_dict = {}
        
        self.enabled = config_dict.get('enabled', False)
        self.video_files = config_dict.get('video_files', [])
        self.rtsp_port = config_dict.get('rtsp_port', 8554)
        self.fps = config_dict.get('fps', 15)
        self.width = config_dict.get('width', 1920)
        self.height = config_dict.get('height', 1080)
        self.bitrate = config_dict.get('bitrate', '2M')
        self.codec = config_dict.get('codec', 'libx264')
        self.preset = config_dict.get('preset', 'fast')
        self.loop_enabled = config_dict.get('loop_enabled', True)
        self.stream_type = config_dict.get('stream_type', 'rtsp')
        
        # tc 기반 네트워크 시뮬레이션 설정
        self.packet_loss = config_dict.get('packet_loss', 0)      # 패킷 손실률 (0-100%)
        self.network_delay = config_dict.get('network_delay', 0)  # 네트워크 지연 (ms)
        self.network_jitter = config_dict.get('network_jitter', 0) # 네트워크 지터 (ms)
        self.bandwidth_limit = config_dict.get('bandwidth_limit', 0) # 대역폭 제한 (Mbps, 0=제한없음)
        
        # 추가 설정
        self.rtmp_port = config_dict.get('rtmp_port', 1935)
        self.server_ip = config_dict.get('server_ip', '127.0.0.1')

def get_local_ip() -> str:
    """로컬 네트워크 IP 주소 가져오기"""
    try:
        result = subprocess.run(['hostname', '-I'], capture_output=True, text=True)
        if result.returncode == 0:
            ips = result.stdout.strip().split()
            if ips:
                return ips[0]
    except Exception:
        pass
    
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        pass
    
    return "127.0.0.1"

def check_ffmpeg() -> bool:
    """FFmpeg 설치 확인"""
    try:
        result = subprocess.run(['ffmpeg', '-version'], 
                              capture_output=True, text=True, timeout=5)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False

def check_sudo_permissions():
    """sudo 권한 확인"""
    try:
        result = subprocess.run(['sudo', '-n', 'true'], capture_output=True)
        return result.returncode == 0
    except:
        return False

def rtsp_sender_process_tc(stream_id: int, config: RTSPStreamConfig, 
                          status_queue: Queue, stop_event: Event, 
                          network_sim: NetworkSimulator):
    """tc 기반 RTSP 송출 프로세스"""
    process_logger = logging.getLogger(f"RTSP_SENDER_TC_{stream_id}")
    current_pid = os.getpid()
    process_logger.info(f"tc 기반 RTSP 송출 프로세스 시작 - PID: {current_pid}")
    
    status_queue.put((stream_id, 'pid', current_pid))
    
    # 재생할 파일 목록 확인
    files_to_play = config.video_files
    if not files_to_play or not any(os.path.exists(f) for f in files_to_play):
        process_logger.error(f"재생 가능한 비디오 파일이 없습니다: {files_to_play}")
        status_queue.put((stream_id, 'error', f"재생 가능한 파일 없음"))
        return
    
    valid_files = [f for f in files_to_play if os.path.exists(f)]
    
    try:
        # 가상 네트워크 인터페이스 설정
        target_ip = config.server_ip
        target_port = config.rtmp_port
        
        if not network_sim.setup_virtual_interface(stream_id, target_ip, target_port):
            process_logger.error(f"가상 인터페이스 설정 실패")
            status_queue.put((stream_id, 'error', "가상 인터페이스 설정 실패"))
            return
        
        # 네트워크 조건 적용
        if not network_sim.apply_network_conditions(
            stream_id, config.packet_loss, config.network_delay, 
            config.network_jitter, config.bandwidth_limit):
            process_logger.error(f"네트워크 조건 적용 실패")
            status_queue.put((stream_id, 'error', "네트워크 조건 적용 실패"))
            return
        
        # 파일 목록을 concat 파일로 생성
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            for file_path in valid_files:
                normalized_path = os.path.abspath(file_path)
                f.write(f"file '{normalized_path}'\n")
            concat_file = f.name
        
        process_logger.info(f"Concat 파일 생성: {concat_file} (파일 수: {len(valid_files)})")
        
        # 네트워크 시뮬레이션 정보 로그
        if config.packet_loss > 0:
            process_logger.info(f"스트림 {stream_id} tc 패킷 손실 {config.packet_loss}% 적용됨")
        if config.network_delay > 0:
            process_logger.info(f"스트림 {stream_id} tc 네트워크 지연 {config.network_delay}ms 적용됨")
        if config.network_jitter > 0:
            process_logger.info(f"스트림 {stream_id} tc 네트워크 지터 {config.network_jitter}ms 적용됨")
        if config.bandwidth_limit > 0:
            process_logger.info(f"스트림 {stream_id} tc 대역폭 제한 {config.bandwidth_limit}Mbps 적용됨")
        
        # 스트리밍 방식 선택
        if config.stream_type == "rtsp":
            rtmp_port = config.rtmp_port
            rtsp_port = config.rtsp_port
            
            # MediaMTX 연결 상태 확인
            mediamtx_ready = False
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(2)
                    result = s.connect_ex(('127.0.0.1', rtmp_port))
                    mediamtx_ready = (result == 0)
            except:
                pass
            
            if not mediamtx_ready:
                process_logger.error(f"MediaMTX 인스턴스 {stream_id}가 RTMP 포트 {rtmp_port}에서 대기하지 않습니다!")
                status_queue.put((stream_id, 'error', f"MediaMTX 포트 {rtmp_port} 연결 불가"))
                return
            
            # 가상 인터페이스를 통한 출력으로 FFmpeg 명령어 구성
            veth_ip = network_sim.get_interface_ip(stream_id)
            if not veth_ip:
                process_logger.error(f"가상 인터페이스 IP 주소를 가져올 수 없습니다")
                status_queue.put((stream_id, 'error', "가상 인터페이스 IP 오류"))
                return
            
            cmd = [
                'ffmpeg', '-y',
                '-f', 'concat',
                '-safe', '0',
                '-stream_loop', '-1',
                '-re',
                '-i', concat_file,
                
                # 비디오 인코딩 설정 (tc 사용시 단순화)
                '-c:v', 'libx264',
                '-preset', 'ultrafast',
                '-tune', 'zerolatency',
                '-profile:v', 'baseline',
                '-level', '3.1',
                
                # 비트레이트 설정
                '-b:v', str(config.bitrate),
                '-maxrate', str(config.bitrate),
                '-bufsize', f'{int(config.bitrate[:-1]) * 2}M' if config.bitrate.endswith('M') else '4M',
                
                # 프레임 설정
                '-r', str(config.fps),
                '-g', str(config.fps),
                '-keyint_min', str(config.fps),
                
                # 픽셀 포맷
                '-pix_fmt', 'yuv420p',
                
                # 오디오 비활성화
                '-an',
                
                # 가상 인터페이스를 통한 RTMP 출력
                '-f', 'flv',
                f'rtmp://127.0.0.1:{rtmp_port}/live'
            ]
            
            protocol_name = f"RTSP-MediaMTX-TC-{stream_id}"
            connection_url = f"rtsp://{config.server_ip}:{rtsp_port}/live"
            
        else:  # UDP 모드
            process_logger.error("UDP 모드는 tc 버전에서 지원되지 않습니다.")
            status_queue.put((stream_id, 'error', "UDP 모드 미지원"))
            return
        
        process_logger.info(f"스트림 {stream_id} {protocol_name} 스트리밍 시작 (포트 {rtsp_port})")
        process_logger.info(f"연결 URL: {connection_url}")
        process_logger.info(f"tc 네트워크 시뮬레이션: 손실={config.packet_loss}%, "
                          f"지연={config.network_delay}ms, 지터={config.network_jitter}ms, "
                          f"대역폭={config.bandwidth_limit}Mbps")
        
        # FFmpeg 프로세스 시작
        ffmpeg_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )
        
        status_queue.put((stream_id, 'running', 
                        f"PID:{current_pid} | {protocol_name}:{rtsp_port} | TC네트워크시뮬레이션"))
        
        start_time = time.time()
        server_ready = False
        
        # 서버 시작 대기 및 모니터링
        while not stop_event.is_set():
            try:
                output = ffmpeg_process.stdout.readline()
                if output:
                    output = output.strip()
                    
                    if 'frame=' in output and not server_ready:
                        process_logger.info(f"스트림 {stream_id} {protocol_name} 스트리밍 시작됨")
                        server_ready = True
                        status_queue.put((stream_id, 'ready', f"{protocol_name} TC 시뮬레이션 준비됨: {rtsp_port}"))
                    
                    if any(keyword in output.lower() for keyword in ['error', 'failed', 'invalid']):
                        process_logger.warning(f"스트림 {stream_id}: {output}")
                    elif 'frame=' in output and int(time.time()) % 30 == 0:
                        process_logger.info(f"스트림 {stream_id}: {output}")
                            
            except Exception as e:
                process_logger.error(f"출력 읽기 오류: {e}")
            
            poll_result = ffmpeg_process.poll()
            if poll_result is not None:
                process_logger.error(f"스트림 {stream_id} FFmpeg 종료됨 (코드: {poll_result})")
                status_queue.put((stream_id, 'error', f"FFmpeg 종료 (코드: {poll_result})"))
                break
            
            # 주기적 상태 업데이트
            runtime = time.time() - start_time
            if int(runtime) % 60 == 0:
                status_text = f"PID:{current_pid} | {protocol_name}:{rtsp_port} | TC시뮬레이션 | 실행:{runtime:.0f}초"
                if server_ready:
                    status_text += " | 스트리밍 중"
                status_queue.put((stream_id, 'running', status_text))
            
            time.sleep(0.1)
            
    except Exception as e:
        process_logger.error(f"스트리밍 오류: {e}")
        status_queue.put((stream_id, 'error', str(e)))
    
    finally:
        # 프로세스 정리
        try:
            if 'ffmpeg_process' in locals() and ffmpeg_process:
                if ffmpeg_process.poll() is None:
                    process_logger.info(f"스트림 {stream_id} FFmpeg 프로세스 종료 중...")
                    ffmpeg_process.terminate()
                    try:
                        ffmpeg_process.wait(timeout=10)
                        process_logger.info(f"FFmpeg 프로세스 정상 종료 (PID: {current_pid})")
                    except subprocess.TimeoutExpired:
                        process_logger.warning(f"FFmpeg 프로세스 강제 종료 (PID: {current_pid})")
                        ffmpeg_process.kill()
                        ffmpeg_process.wait()
        except Exception as e:
            process_logger.error(f"FFmpeg 프로세스 종료 오류: {e}")
        
        # 가상 인터페이스 정리
        network_sim.cleanup_virtual_interface(stream_id)
        
        # 임시 파일 정리
        try:
            if 'concat_file' in locals():
                os.unlink(concat_file)
                process_logger.info(f"임시 파일 삭제: {concat_file}")
        except Exception as e:
            process_logger.warning(f"임시 파일 삭제 실패: {e}")
        
        status_queue.put((stream_id, 'stopped', f"송출 중지됨 (PID: {current_pid})"))
        process_logger.info(f"tc 기반 스트리밍 프로세스 종료완료 - PID: {current_pid}")

class RTSPSenderManagerTC:
    """tc 기반 RTSP 송출 관리자 클래스"""
    
    def __init__(self, config_path: str = "config.json"):
        self.config_path = config_path
        self.config = None
        self.processes = {}
        self.stop_events = {}
        self.status_queues = {}
        self.stream_pids = {}
        self.manager = Manager()
        self.running = False
        self.network_sim = NetworkSimulator()
        
        # 시그널 핸들러 등록
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        logger.info("tc 기반 RTSP 송출 관리자가 초기화되었습니다.")
    
    def _signal_handler(self, signum, frame):
        """시그널 핸들러"""
        logger.info(f"시그널 {signum} 수신됨. 프로그램을 종료합니다...")
        self.stop_all_streams()
        sys.exit(0)
    
    def check_system_requirements(self):
        """시스템 요구사항 확인"""
        logger.info("시스템 요구사항 확인 중...")
        
        # tc 지원 확인
        if not self.network_sim.check_tc_support():
            logger.error("tc(Traffic Control) 명령어를 찾을 수 없습니다.")
            logger.error("설치 방법: sudo apt install iproute2")
            return False
        
        # sudo 권한 확인
        if not check_sudo_permissions():
            logger.error("sudo 권한이 필요합니다.")
            logger.error("다음 명령어로 실행하세요: sudo python3 rtsp_sender_tc.py")
            return False
        
        # FFmpeg 확인
        if not check_ffmpeg():
            logger.error("FFmpeg가 설치되지 않았습니다.")
            logger.error("설치 방법: sudo apt install ffmpeg")
            return False
        
        logger.info("✅ 모든 시스템 요구사항이 만족되었습니다.")
        return True
    
    def load_config(self) -> bool:
        """설정 파일 로드"""
        if not os.path.exists(self.config_path):
            logger.error(f"설정 파일이 없습니다: {self.config_path}")
            return False
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            logger.info(f"설정 파일을 로드했습니다: {self.config_path}")
            return True
        except Exception as e:
            logger.error(f"설정 파일 로드 실패: {e}")
            return False
    
    def validate_config(self) -> bool:
        """설정 파일 유효성 검사"""
        if not self.config:
            logger.error("설정이 로드되지 않았습니다.")
            return False
        
        streams = self.config.get('streams', [])
        if not streams:
            logger.error("스트림 설정이 없습니다.")
            return False
        
        enabled_streams = [s for s in streams if s.get('enabled', False)]
        if not enabled_streams:
            logger.warning("활성화된 스트림이 없습니다.")
            return False
        
        # 파일 존재 확인
        for stream in enabled_streams:
            video_files = stream.get('video_files', [])
            if not video_files:
                logger.error(f"스트림 {stream.get('stream_id', '?')}: 비디오 파일이 지정되지 않았습니다.")
                return False
            
            for video_file in video_files:
                if not os.path.exists(video_file):
                    logger.error(f"스트림 {stream.get('stream_id', '?')}: 비디오 파일이 존재하지 않습니다: {video_file}")
                    return False
        
        return True
    
    def start_stream(self, stream_config: Dict) -> bool:
        """개별 스트림 시작"""
        stream_id = stream_config.get('stream_id', 0)
        
        if stream_id in self.processes and self.processes[stream_id].is_alive():
            logger.warning(f"스트림 {stream_id}이 이미 실행 중입니다.")
            return False
        
        config = RTSPStreamConfig(stream_config)
        
        # 프로세스 시작
        stop_event = Event()
        status_queue = Queue()
        
        process = Process(
            target=rtsp_sender_process_tc,
            args=(stream_id, config, status_queue, stop_event, self.network_sim),
            name=f"RTSPSenderTC_{stream_id}"
        )
        
        process.start()
        
        self.processes[stream_id] = process
        self.stop_events[stream_id] = stop_event
        self.status_queues[stream_id] = status_queue
        
        logger.info(f"tc 기반 스트림 {stream_id} 시작됨 (PID: {process.pid})")
        return True
    
    def stop_stream(self, stream_id: int) -> bool:
        """개별 스트림 중지"""
        if stream_id in self.stop_events:
            self.stop_events[stream_id].set()
        
        if stream_id in self.processes:
            process = self.processes[stream_id]
            if process.is_alive():
                try:
                    process.join(timeout=10)
                    if process.is_alive():
                        process.terminate()
                        process.join(timeout=5)
                        if process.is_alive():
                            process.kill()
                            process.join()
                    logger.info(f"tc 기반 스트림 {stream_id} 중지됨")
                except Exception as e:
                    logger.error(f"스트림 {stream_id} 중지 오류: {e}")
            
            if stream_id in self.stream_pids:
                del self.stream_pids[stream_id]
            
            del self.processes[stream_id]
            del self.stop_events[stream_id]
            del self.status_queues[stream_id]
            return True
        
        return False
    
    def start_all_streams(self) -> bool:
        """모든 활성화된 스트림 시작"""
        if not self.config:
            logger.error("설정이 로드되지 않았습니다.")
            return False
        
        streams = self.config.get('streams', [])
        enabled_streams = [s for s in streams if s.get('enabled', False)]
        
        if not enabled_streams:
            logger.warning("활성화된 스트림이 없습니다.")
            return False
        
        success_count = 0
        for stream_config in enabled_streams:
            if self.start_stream(stream_config):
                success_count += 1
                time.sleep(2)  # 가상 인터페이스 설정 시간 확보
        
        logger.info(f"총 {success_count}/{len(enabled_streams)}개 tc 기반 스트림이 시작되었습니다.")
        self.running = True
        return success_count > 0
    
    def stop_all_streams(self):
        """모든 스트림 중지"""
        if not self.processes:
            logger.info("실행 중인 스트림이 없습니다.")
            return
        
        stopped_count = 0
        running_streams = list(self.processes.keys())
        
        for stream_id in running_streams:
            if self.stop_stream(stream_id):
                stopped_count += 1
        
        # 모든 가상 인터페이스 정리
        self.network_sim.cleanup_all_interfaces()
        
        logger.info(f"총 {stopped_count}개 tc 기반 스트림이 중지되었습니다.")
        self.running = False
    
    def monitor_streams(self):
        """스트림 상태 모니터링"""
        logger.info("tc 기반 스트림 모니터링을 시작합니다...")
        
        while self.running:
            try:
                running_count = 0
                
                for stream_id in list(self.status_queues.keys()):
                    try:
                        while True:
                            sid, status, message = self.status_queues[stream_id].get_nowait()
                            
                            if status == 'pid':
                                self.stream_pids[stream_id] = message
                                logger.info(f"tc 스트림 {stream_id} PID: {message}")
                            elif status == 'running':
                                running_count += 1
                                if int(time.time()) % 300 == 0:  # 5분마다 로그
                                    logger.info(f"tc 스트림 {stream_id} 실행 중: {message}")
                            elif status == 'ready':
                                logger.info(f"tc 스트림 {stream_id} 준비됨: {message}")
                                running_count += 1
                            elif status == 'error':
                                logger.error(f"tc 스트림 {stream_id} 오류: {message}")
                            elif status == 'stopped':
                                logger.info(f"tc 스트림 {stream_id} 중지됨: {message}")
                    except:
                        if stream_id in self.processes and self.processes[stream_id].is_alive():
                            running_count += 1
                
                # 5분마다 전체 상태 로그
                if int(time.time()) % 300 == 0:
                    if running_count > 0:
                        active_pids = list(self.stream_pids.values())
                        logger.info(f"📡 총 {running_count}개 tc 기반 스트림 송출 중 (PID: {active_pids})")
                    else:
                        logger.info("⭕ 실행 중인 tc 기반 스트림이 없습니다.")
                
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"모니터링 오류: {e}")
                time.sleep(5)
        
        logger.info("tc 기반 스트림 모니터링이 종료되었습니다.")
    
    def run(self) -> bool:
        """메인 실행 함수"""
        # 시스템 요구사항 확인
        if not self.check_system_requirements():
            return False
        
        # 설정 로드
        if not self.load_config():
            return False
        
        # 설정 유효성 검사
        if not self.validate_config():
            return False
        
        # 모든 스트림 시작
        if not self.start_all_streams():
            logger.error("tc 기반 스트림을 시작할 수 없습니다.")
            return False
        
        # 모니터링 스레드 시작
        monitor_thread = threading.Thread(target=self.monitor_streams, daemon=True)
        monitor_thread.start()
        
        logger.info("모든 tc 기반 스트림이 시작되었습니다. Ctrl+C로 종료하세요.")
        
        try:
            # 메인 루프
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("키보드 인터럽트 수신. 종료 중...")
        finally:
            self.stop_all_streams()
        
        logger.info("tc 기반 프로그램이 종료되었습니다.")
        return True

def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description="tc 기반 다중 RTSP 영상 송출 프로그램")
    parser.add_argument('-c', '--config', default='config.json', help='설정 파일 경로 (기본값: config.json)')
    parser.add_argument('--check-system', action='store_true', help='시스템 요구사항 확인')
    
    args = parser.parse_args()
    
    # 멀티프로세싱 설정
    if hasattr(mp, 'set_start_method'):
        try:
            mp.set_start_method('spawn', force=True)
        except RuntimeError:
            pass
    
    # 시스템 요구사항 확인
    if args.check_system:
        print("=== tc 기반 RTSP 송출 시스템 요구사항 확인 ===")
        
        # tc 확인
        network_sim = NetworkSimulator()
        tc_ok = network_sim.check_tc_support()
        print(f"tc (Traffic Control): {'✅ 설치됨' if tc_ok else '❌ 미설치'}")
        if not tc_ok:
            print("  └ 설치 방법: sudo apt install iproute2")
        
        # sudo 권한 확인
        sudo_ok = check_sudo_permissions()
        print(f"sudo 권한: {'✅ 사용 가능' if sudo_ok else '❌ 권한 없음'}")
        if not sudo_ok:
            print("  └ 해결 방법: sudo python3 rtsp_sender_tc.py 로 실행")
        
        # FFmpeg 확인
        ffmpeg_ok = check_ffmpeg()
        print(f"FFmpeg: {'✅ 설치됨' if ffmpeg_ok else '❌ 미설치'}")
        if not ffmpeg_ok:
            print("  └ 설치 방법: sudo apt install ffmpeg")
        
        print(f"네트워크 IP: {get_local_ip()}")
        print()
        
        if tc_ok and sudo_ok and ffmpeg_ok:
            print("✅ 모든 요구사항이 만족되었습니다.")
            print("sudo python3 rtsp_sender_tc.py 로 실행하세요.")
        else:
            print("❌ 일부 요구사항이 만족되지 않았습니다.")
        return
    
    # 메인 프로그램 실행
    manager = RTSPSenderManagerTC(args.config)
    success = manager.run()
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()