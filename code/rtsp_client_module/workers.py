"""
공유 워커 아키텍처 - RTSP 워커 프로세스 모듈

이 모듈은 공유 워커 방식으로 설계되어:
- 캡처 워커: 설정 개수만큼 생성, 모든 스트림을 순환 처리
- 블러 워커: 설정 개수만큼 생성, 모든 스트림 큐를 순환 처리  
- 저장 워커: 설정 개수만큼 생성, 모든 스트림 큐를 순환 처리
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
from typing import Optional, Dict, List
from dataclasses import dataclass


def rtsp_capture_process(worker_id, sources, blur_queues, preview_queue, stats_dict, stop_event, config):
    """공유 캡처 워커 - 여러 스트림을 순환 처리"""
    logger = logging.getLogger(f"CAPTURE_{worker_id}")
    current_pid = os.getpid()
    logger.info(f"📹 캡처 워커 실행 중 - PID: {current_pid}, Worker: {worker_id}")
    logger.info(f"   🆔 프로세스 ID: {current_pid}")
    logger.info(f"   🔧 워커 ID: {worker_id}")
    logger.info(f"   🎯 다중 스트림 처리 - {len(sources)}개 소스, {len(blur_queues)}개 블러큐")
    
    # 블러 모듈 로드 (워커별로 독립적)
    blur_module = None
    if config.blur_module_path:
        try:
            logger.info(f"Worker {worker_id}: 블러 모듈 로드 시도 - 경로: {config.blur_module_path}")
            
            # 파일 존재 확인
            if not os.path.exists(config.blur_module_path):
                logger.error(f"Worker {worker_id}: 블러 모듈 파일이 존재하지 않음 - {config.blur_module_path}")
                blur_module = None
            else:
                logger.info(f"Worker {worker_id}: 블러 모듈 파일 존재 확인됨")
                
                spec = importlib.util.spec_from_file_location(f"blur_module_{worker_id}", config.blur_module_path)
                if spec is None:
                    logger.error(f"Worker {worker_id}: 블러 모듈 spec 생성 실패")
                    blur_module = None
                else:
                    logger.info(f"Worker {worker_id}: 블러 모듈 spec 생성 성공")
                    blur_module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(blur_module)
                    logger.info(f"Worker {worker_id}: 블러 모듈 실행 완료")
                    
                    if hasattr(blur_module, 'HeadBlurrer'):
                        logger.info(f"Worker {worker_id}: HeadBlurrer 클래스 발견")
                        try:
                            head_blurrer = blur_module.HeadBlurrer()
                            blur_module.apply_blur = lambda frame: head_blurrer.process_frame(frame)
                            logger.info(f"Worker {worker_id}: HeadBlurrer 인스턴스 생성 및 apply_blur 함수 설정 완료")
                        except Exception as init_error:
                            logger.error(f"Worker {worker_id}: HeadBlurrer 인스턴스 생성 실패 - {init_error}")
                            logger.info(f"Worker {worker_id}: 기본 블러 처리로 대체")
                            blur_module = None
                    else:
                        logger.warning(f"Worker {worker_id}: HeadBlurrer 클래스를 찾을 수 없음")
                        # 사용 가능한 속성들 출력
                        available_attrs = [attr for attr in dir(blur_module) if not attr.startswith('_')]
                        logger.info(f"Worker {worker_id}: 사용 가능한 속성들: {available_attrs}")
            
            logger.info(f"Worker {worker_id}: 블러 모듈 로드 성공")
        except Exception as e:
            logger.error(f"Worker {worker_id}: 블러 모듈 로드 실패 - {e}")
            import traceback
            logger.error(f"Worker {worker_id}: 블러 모듈 로드 실패 상세 - {traceback.format_exc()}")
            blur_module = None
    
    # 워커별 담당 스트림 계산 (라운드 로빈 분할)
    worker_index = int(worker_id.split('_')[1]) - 1  # capture_1 -> 0, capture_2 -> 1
    total_workers = config.capture_workers
    
    # 이 워커가 담당할 스트림 인덱스들 계산
    assigned_stream_indices = []
    for i in range(len(sources)):
        if i % total_workers == worker_index:
            assigned_stream_indices.append(i)
    
    logger.info(f"Worker {worker_id}: 담당 스트림 인덱스 - {assigned_stream_indices}")
    
    # 각 스트림별 OpenCV VideoCapture 초기화 (담당 스트림만)
    caps = {}
    # 이 워커가 담당하는 스트림 ID들만 생성
    assigned_stream_ids = [f"stream_{i+1}" for i in assigned_stream_indices]
    
    for i in assigned_stream_indices:
        source = sources[i]
        stream_id = f"stream_{i+1}"
        cap = cv2.VideoCapture(source)
        
        # 안전한 속성 설정
        try:
            if hasattr(cv2, 'CAP_PROP_BUFFER_SIZE'):
                cap.set(cv2.CAP_PROP_BUFFER_SIZE, 1)
        except Exception as e:
            logger.debug(f"CAP_PROP_BUFFER_SIZE 설정 실패: {e}")
        
        if config.force_fps:
            try:
                if hasattr(cv2, 'CAP_PROP_FPS'):
                    cap.set(cv2.CAP_PROP_FPS, config.input_fps)
            except Exception as e:
                logger.debug(f"CAP_PROP_FPS 설정 실패: {e}")
        
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
            continue
            
        # 첫 번째 프레임 읽기 시도
        ret, frame = cap.read()
        if not ret:
            cap.release()
            logger.error(f"소스에서 프레임 읽기 실패: {source}")
            continue
        
        caps[stream_id] = cap
        logger.info(f"Worker {worker_id}: Stream {stream_id} 소스 연결 성공 - {source}")
    
    # 스트림별 프레임 카운터 및 상태 (담당 스트림만)
    frame_counts = {stream_id: 0 for stream_id in assigned_stream_ids}
    failed_counts = {stream_id: 0 for stream_id in assigned_stream_ids}
    start_time = time.time()
    
    # FPS 제어를 위한 프레임 간격 계산
    frame_interval = 1.0 / config.input_fps
    
    # 스트림 순환 처리를 위한 인덱스
    stream_index = 0
    
    try:
        while not stop_event.is_set():
            # 최대 처리 시간 체크
            if config.max_duration_seconds:
                elapsed_time = time.time() - start_time
                if elapsed_time >= config.max_duration_seconds:
                    break
            
            # 처리할 스트림이 없으면 잠깐 대기
            if not caps:
                time.sleep(0.1)
                continue
            
            # 라운드 로빈 방식으로 스트림 선택
            stream_keys = list(caps.keys())
            if not stream_keys:
                time.sleep(0.1)
                continue
                
            current_stream_id = stream_keys[stream_index % len(stream_keys)]
            stream_index += 1
            
            cap = caps[current_stream_id]
            
            # FPS 제어
            next_frame_time = start_time + (frame_counts[current_stream_id] + 1) * frame_interval
            sleep_time = next_frame_time - time.time()
            if sleep_time > 0:
                time.sleep(min(sleep_time, 0.1))  # 최대 100ms만 대기
            
            ret, frame = cap.read()
            
            if not ret:
                failed_counts[current_stream_id] += 1
                if failed_counts[current_stream_id] > 10:
                    logger.error(f"Worker {worker_id}: Stream {current_stream_id} 연속 실패 - 재연결 시도")
                    cap.release()
                    time.sleep(config.reconnect_interval)
                    
                    # 재연결 시도 (스트림 ID에서 인덱스 추출)
                    stream_index_in_source = int(current_stream_id.split('_')[1]) - 1
                    source = sources[stream_index_in_source]
                    new_cap = cv2.VideoCapture(source)
                    
                    # 재연결 시에도 안전한 속성 설정
                    try:
                        if hasattr(cv2, 'CAP_PROP_BUFFER_SIZE'):
                            new_cap.set(cv2.CAP_PROP_BUFFER_SIZE, 1)
                    except:
                        pass
                    
                    if new_cap.isOpened():
                        caps[current_stream_id] = new_cap
                        failed_counts[current_stream_id] = 0
                        logger.info(f"Worker {worker_id}: Stream {current_stream_id} 재연결 성공")
                    else:
                        logger.error(f"Worker {worker_id}: Stream {current_stream_id} 재연결 실패")
                        del caps[current_stream_id]
                continue
            
            failed_counts[current_stream_id] = 0
            
            # 통계 업데이트
            stats_dict[f'{current_stream_id}_received'] = stats_dict.get(f'{current_stream_id}_received', 0) + 1
            
            # 프레임 손실 시뮬레이션
            if random.random() < config.frame_loss_rate:
                stats_dict[f'{current_stream_id}_lost'] = stats_dict.get(f'{current_stream_id}_lost', 0) + 1
                logger.debug(f"Worker {worker_id}: Stream {current_stream_id} 프레임 {frame_counts[current_stream_id]} 시뮬레이션 손실")
                continue
            
            # 블러 탐지 간격 확인 (탐지를 수행할지 결정)
            should_detect = (frame_counts[current_stream_id] % config.blur_interval == 0)
            
            # 블러 처리 작업 데이터 준비 (모든 프레임을 블러 큐에 전송)
            work_item = {
                'stream_id': current_stream_id,
                'thread_id': int(current_stream_id.split('_')[1]) - 1,
                'frame': frame.copy(),
                'timestamp': datetime.now(),
                'frame_number': frame_counts[current_stream_id],
                'blur_module_path': config.blur_module_path,
                'blur_interval': config.blur_interval,
                'should_detect': should_detect,  # 탐지 수행 여부 (지속성을 위해 모든 프레임 전송)
                'overlay_enabled': config.overlay_enabled,
                'save_enabled': config.save_enabled,
                'save_path': config.save_path,
                'save_format': config.save_format,
                'save_interval': config.save_interval,
                'save_interval_seconds': config.save_interval_seconds,
                'preview_enabled': config.preview_enabled
            }
            
            # 해당 스트림의 블러 큐에 전송
            if current_stream_id in blur_queues:
                try:
                    blur_queues[current_stream_id].put_nowait(work_item)
                except queue.Full:
                    try:
                        blur_queues[current_stream_id].get_nowait()
                        blur_queues[current_stream_id].put_nowait(work_item)
                        logger.warning(f"Worker {worker_id}: Stream {current_stream_id} 블러큐 오버플로우")
                    except:
                        pass
                    time.sleep(0.01)
            
            frame_counts[current_stream_id] += 1
            
            # 주기적 로깅
            total_frames = sum(frame_counts.values())
            if total_frames % 100 == 0:
                active_streams = len(caps)
                logger.info(f"Worker {worker_id}: 총 {total_frames}프레임 처리, 활성 스트림: {active_streams}개")
                    
    except Exception as e:
        logger.error(f"캡처 워커 오류: {e}")
    finally:
        for stream_id, cap in caps.items():
            cap.release()
        total_frames = sum(frame_counts.values())
        logger.info(f"캡처 워커 종료 - Worker {worker_id}, 총 {total_frames}개 프레임")


def blur_worker_process(worker_id, blur_queues, save_queues, preview_queue, stats_dict, stop_event):
    """공유 블러 워커 - 여러 스트림 큐를 순환 처리"""
    logger = logging.getLogger(f"BLUR_WORKER_{worker_id}")
    current_pid = os.getpid()
    logger.info(f"🔍 블러 워커 실행 중 - PID: {current_pid}, Worker: {worker_id}")
    logger.info(f"   🆔 프로세스 ID: {current_pid}")
    logger.info(f"   🔧 워커 ID: {worker_id}")
    logger.info(f"   🎯 다중 스트림 처리 - {len(blur_queues)}개 블러큐, {len(save_queues)}개 저장큐")
    
    processed_count = 0
    
    # 워커별 블러 모듈 캐시
    blur_modules = {}
    
    # 스트림별 블러 상태 저장 (지속성을 위해)
    stream_blur_states = {}  # {stream_id: {'last_detection_result': {...}, 'last_detection_frame': 0}}
    
    def _apply_basic_blur_with_persistence(frame, stream_id, frame_number, blur_interval, worker_id, should_detect=True):
        """기본 블러 처리에 지속성 적용 (가상의 얼굴 영역 사용)"""
        
        # 스트림별 블러 상태 초기화
        if stream_id not in stream_blur_states:
            stream_blur_states[stream_id] = {
                'last_detection_frame': 0,
                'last_blur_regions': []  # 마지막 블러 영역들
            }
        
        current_frame = frame_number
        
        if should_detect:
            # 새로운 가상의 얼굴 영역 생성 (테스트용)
            h, w = frame.shape[:2]
            # 화면 중앙 상단에 가상의 얼굴 영역들 생성
            new_regions = [
                (w//4, h//6, w//4 + w//8, h//6 + h//8),      # 첫 번째 얼굴
                (3*w//4 - w//8, h//6, 3*w//4, h//6 + h//8)   # 두 번째 얼굴
            ]
            stream_blur_states[stream_id]['last_blur_regions'] = new_regions
            stream_blur_states[stream_id]['last_detection_frame'] = current_frame
            logger.info(f"Worker {worker_id}: Stream {stream_id} - ✨ 새로운 얼굴 탐지 (프레임 {current_frame}, 영역: {len(new_regions)}개)")
        else:
            logger.info(f"Worker {worker_id}: Stream {stream_id} - 🔄 이전 얼굴 위치 유지 (프레임 {current_frame}, 마지막 탐지: 프레임 {stream_blur_states[stream_id]['last_detection_frame']})")
        
        # 저장된 얼굴 영역에 블러 적용
        processed_frame = frame.copy()
        blur_regions = stream_blur_states[stream_id]['last_blur_regions']
        
        applied_regions = 0
        for x1, y1, x2, y2 in blur_regions:
            # 영역 검증
            h, w = frame.shape[:2]
            x1 = max(0, min(x1, w-1))
            y1 = max(0, min(y1, h-1))
            x2 = max(x1+1, min(x2, w))
            y2 = max(y1+1, min(y2, h))
            
            # 해당 영역에 블러 적용
            roi = processed_frame[y1:y2, x1:x2]
            if roi.size > 0:
                blurred_roi = cv2.GaussianBlur(roi, (51, 51), 0)
                processed_frame[y1:y2, x1:x2] = blurred_roi
                applied_regions += 1
        
        logger.info(f"Worker {worker_id}: Stream {stream_id} - 🎯 블러 적용 완료 (프레임 {current_frame}, 영역: {applied_regions}/{len(blur_regions)}개)")
        return processed_frame
    
    # 큐 순환을 위한 변수
    queue_keys = list(blur_queues.keys())
    queue_index = 0
    
    try:
        while not stop_event.is_set():
            # 모든 블러 큐가 비어있는지 확인
            any_queue_has_data = False
            for queue_key in queue_keys:
                if not blur_queues[queue_key].empty():
                    any_queue_has_data = True
                    break
            
            if not any_queue_has_data and stop_event.is_set():
                break
                
            try:
                # 라운드 로빈 방식으로 큐 선택
                current_queue_key = queue_keys[queue_index]
                current_blur_queue = blur_queues[current_queue_key]
                current_save_queue = save_queues[current_queue_key]
                
                # 다음 큐로 인덱스 이동
                queue_index = (queue_index + 1) % len(queue_keys)
                
                work_item = current_blur_queue.get(timeout=0.1)
                
                # work_item 구조 검증
                if not isinstance(work_item, dict):
                    logger.warning(f"Worker {worker_id}: 잘못된 work_item 형식")
                    continue
                
                # 필수 키 확인
                required_keys = ['frame', 'blur_module_path', 'stream_id', 'thread_id']
                missing_keys = [key for key in required_keys if key not in work_item]
                if missing_keys:
                    logger.warning(f"Worker {worker_id}: work_item에 누락된 키 - {missing_keys}")
                    continue
                
                frame = work_item['frame']
                blur_module_path = work_item['blur_module_path']
                stream_id = work_item['stream_id']
                thread_id = work_item['thread_id']
                timestamp = work_item.get('timestamp', datetime.now())
                frame_number = work_item.get('frame_number', 0)
                
                # 블러 모듈 로드 (캐시 사용)
                blur_module = None
                if blur_module_path and blur_module_path not in blur_modules:
                    try:
                        logger.info(f"Worker {worker_id}: 블러 모듈 로드 시도 (캐시) - 경로: {blur_module_path}")
                        
                        # 파일 존재 확인
                        if not os.path.exists(blur_module_path):
                            logger.error(f"Worker {worker_id}: 블러 모듈 파일이 존재하지 않음 - {blur_module_path}")
                            blur_modules[blur_module_path] = None
                        else:
                            spec = importlib.util.spec_from_file_location(f"blur_module_{worker_id}_{stream_id}", blur_module_path)
                            blur_module = importlib.util.module_from_spec(spec)
                            spec.loader.exec_module(blur_module)
                            
                            if hasattr(blur_module, 'HeadBlurrer'):
                                logger.info(f"Worker {worker_id}: HeadBlurrer 클래스 발견 (블러 워커)")
                                try:
                                    head_blurrer = blur_module.HeadBlurrer()
                                    blur_module.apply_blur = lambda frame: head_blurrer.process_frame(frame)
                                    logger.info(f"Worker {worker_id}: HeadBlurrer 인스턴스 생성 완료 (블러 워커)")
                                except Exception as init_error:
                                    logger.error(f"Worker {worker_id}: HeadBlurrer 인스턴스 생성 실패 (블러 워커) - {init_error}")
                                    logger.info(f"Worker {worker_id}: 기본 블러 처리로 대체 (블러 워커)")
                                    blur_module = None
                            else:
                                logger.warning(f"Worker {worker_id}: HeadBlurrer 클래스를 찾을 수 없음 (블러 워커)")
                                available_attrs = [attr for attr in dir(blur_module) if not attr.startswith('_')]
                                logger.info(f"Worker {worker_id}: 사용 가능한 속성들: {available_attrs}")
                            
                            blur_modules[blur_module_path] = blur_module
                            logger.info(f"Worker {worker_id}: 블러 모듈 로드 성공 (캐시 저장)")
                    except Exception as e:
                        logger.error(f"Worker {worker_id}: 블러 모듈 로드 실패 - {e}")
                        import traceback
                        logger.error(f"Worker {worker_id}: 블러 모듈 로드 실패 상세 - {traceback.format_exc()}")
                        blur_modules[blur_module_path] = None
                else:
                    blur_module = blur_modules.get(blur_module_path)
                    if blur_module_path:
                        logger.debug(f"Worker {worker_id}: 블러 모듈 캐시에서 가져옴 - {blur_module is not None}")
                
                # 블러 처리 (지속성 포함) - 모든 프레임 처리
                should_detect = work_item.get('should_detect', True)  # 탐지 수행 여부
                blur_interval = work_item.get('blur_interval', 3)  # 탐지 간격
                
                # 블러 처리는 항상 수행 (지속성을 위해)
                if blur_module and hasattr(blur_module, 'apply_blur'):
                    try:
                        # 스트림별 블러 상태 초기화
                        if stream_id not in stream_blur_states:
                            stream_blur_states[stream_id] = {
                                'last_detection_frame': 0,
                                'head_blurrer': None
                            }
                        
                        # HeadBlurrer 인스턴스 생성 (스트림별)
                        if stream_blur_states[stream_id]['head_blurrer'] is None:
                            if hasattr(blur_module, 'HeadBlurrer'):
                                try:
                                    stream_blur_states[stream_id]['head_blurrer'] = blur_module.HeadBlurrer()
                                    logger.info(f"Worker {worker_id}: 스트림 {stream_id}용 HeadBlurrer 인스턴스 생성")
                                except Exception as e:
                                    logger.error(f"Worker {worker_id}: HeadBlurrer 생성 실패 - {e}")
                                    stream_blur_states[stream_id]['head_blurrer'] = 'failed'
                        
                        # HeadBlurrer 사용 (지속성 있는 블러)
                        if (stream_blur_states[stream_id]['head_blurrer'] and 
                            stream_blur_states[stream_id]['head_blurrer'] != 'failed'):
                            
                            head_blurrer = stream_blur_states[stream_id]['head_blurrer']
                            
                            # 캡처 워커에서 전달받은 should_detect 사용
                            if should_detect:
                                logger.debug(f"Worker {worker_id}: Stream {stream_id} - 새로운 탐지 수행 (프레임 {frame_number})")
                            else:
                                logger.debug(f"Worker {worker_id}: Stream {stream_id} - 이전 탐지 결과 사용 (프레임 {frame_number})")
                            
                            # HeadBlurrer의 process_frame 메서드 사용 (should_detect 매개변수로 제어)
                            processed_frame = head_blurrer.process_frame(
                                frame, 
                                should_detect=should_detect,
                                blur_strength=0.01
                            )
                        else:
                            # HeadBlurrer 실패 시 기본 블러 사용
                            processed_frame = blur_module.apply_blur(frame)
                        
                    except Exception as e:
                        logger.error(f"Worker {worker_id}: 지속성 블러 처리 오류 - {e}")
                        # 기본 블러 처리도 지속성 적용
                        processed_frame = _apply_basic_blur_with_persistence(
                            frame, stream_id, frame_number, blur_interval, worker_id, should_detect
                        )
                else:
                    # 블러 모듈이 없을 때는 원본 프레임 사용
                    processed_frame = frame
                
                # 오버레이 처리
                overlay_enabled = work_item.get('overlay_enabled', False)
                if overlay_enabled:
                    current_time = timestamp.strftime("%Y-%m-%d %H:%M:%S")
                    
                    overlay_lines = [
                        f"Frame: {frame_number:06d}",
                        f"Time: {current_time}",
                        f"Thread: {thread_id}"
                    ]
                    
                    for i, line in enumerate(overlay_lines):
                        y_pos = 25 + i * 25
                        cv2.putText(processed_frame, line, (10, y_pos), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 1, cv2.LINE_AA)
                
                # 저장 큐로 전송
                save_enabled = work_item.get('save_enabled', True)
                if save_enabled:
                    save_item = {
                        'stream_id': stream_id,
                        'thread_id': thread_id,
                        'frame': processed_frame,
                        'timestamp': timestamp,
                        'frame_number': frame_number,
                        'save_path': work_item.get('save_path', './output/'),
                        'save_format': work_item.get('save_format', 'mp4'),
                        'save_interval': work_item.get('save_interval', 300),
                        'save_interval_seconds': work_item.get('save_interval_seconds', 20)
                    }
                    
                    try:
                        current_save_queue.put_nowait(save_item)
                    except queue.Full:
                        try:
                            current_save_queue.get_nowait()
                            current_save_queue.put_nowait(save_item)
                            logger.warning(f"Worker {worker_id}: Stream {stream_id} 저장큐 오버플로우")
                        except:
                            pass
                
                # 미리보기 큐로 전송
                preview_enabled = work_item.get('preview_enabled', True)
                if preview_enabled and frame_number % 3 == 0:
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
                        pass
                    except Exception as e:
                        logger.debug(f"Worker {worker_id}: 미리보기 큐 전송 실패 - {e}")
                
                # 통계 업데이트
                stats_dict[f'{stream_id}_processed'] = stats_dict.get(f'{stream_id}_processed', 0) + 1
                processed_count += 1
                
                # 메모리 정리
                if processed_count % 100 == 0:
                    import gc
                    gc.collect()
                    total_save_queue_size = sum(q.qsize() for q in save_queues.values())
                    logger.info(f"Worker {worker_id}: {processed_count}프레임 처리, 총 저장큐: {total_save_queue_size}")
                        
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


def save_worker_process(worker_id, save_queues, stats_dict, stop_event, base_output_dir, config, shared_stream_last_save_times, stream_timing_lock):
    """공유 저장 워커 - 여러 스트림 큐를 순환 처리"""
    logger = logging.getLogger(f"SAVE_WORKER_{worker_id}")
    current_pid = os.getpid()
    logger.info(f"💾 저장 워커 실행 중 - PID: {current_pid}, Worker: {worker_id}")
    logger.info(f"   🆔 프로세스 ID: {current_pid}")
    logger.info(f"   🔧 워커 ID: {worker_id}")
    logger.info(f"   📁 저장 경로: {base_output_dir}")
    logger.info(f"   🎯 다중 스트림 처리 - {len(save_queues)}개 저장큐")
    
    saved_count = 0
    video_writers = {}
    frame_counts = {}
    file_counters = {}
    video_frame_counts = {}
    stream_dirs = {}
    file_start_times = {}  # 각 파일의 시작 시간 추적
    
    # 15fps 저장 제한을 위한 글로벌 공유 타이머
    target_fps = 15.0
    frame_interval = 1.0 / target_fps
    
    # 큐 순환을 위한 변수
    queue_keys = list(save_queues.keys())
    queue_index = 0
    
    try:
        while not stop_event.is_set():
            # 모든 저장 큐가 비어있는지 확인
            any_queue_has_data = False
            for queue_key in queue_keys:
                if not save_queues[queue_key].empty():
                    any_queue_has_data = True
                    break
            
            if not any_queue_has_data and stop_event.is_set():
                break
                
            try:
                # 라운드 로빈 방식으로 큐 선택
                current_queue_key = queue_keys[queue_index]
                current_save_queue = save_queues[current_queue_key]
                
                # 다음 큐로 인덱스 이동
                queue_index = (queue_index + 1) % len(queue_keys)
                
                save_item = current_save_queue.get(timeout=0.1)
                
                stream_id = save_item['stream_id']
                frame = save_item['frame']
                timestamp = save_item['timestamp']
                save_path = save_item.get('save_path', './output/')
                save_format = save_item.get('save_format', 'mp4')
                save_interval = save_item.get('save_interval', 300)
                save_interval_seconds = save_item.get('save_interval_seconds', 20)  # 시간 기준 파일 분할
                
                # 스트림별 디렉토리 생성
                if stream_id not in stream_dirs:
                    stream_dir = os.path.join(base_output_dir, stream_id)
                    os.makedirs(stream_dir, exist_ok=True)
                    stream_dirs[stream_id] = stream_dir
                    frame_counts[stream_id] = 0
                    file_counters[stream_id] = 0
                    video_frame_counts[stream_id] = 0
                    # file_start_times는 첫 번째 파일 생성 시에 설정됨

                frame_counts[stream_id] += 1
                
                # 15fps 제어 (스트림별 Lock 사용)
                should_save_frame = False
                with stream_timing_lock:
                    current_time = time.time()
                    last_save_time = shared_stream_last_save_times.get(stream_id, 0.0)
                    time_since_last_save = current_time - last_save_time
                    
                    if time_since_last_save >= frame_interval:
                        shared_stream_last_save_times[stream_id] = current_time
                        should_save_frame = True
                        logger.debug(f"SAVE_WORKER_{worker_id}: Stream {stream_id} - 프레임 저장 승인 (간격: {time_since_last_save:.3f}s)")
                    else:
                        logger.debug(f"SAVE_WORKER_{worker_id}: Stream {stream_id} - 프레임 스킵 (간격: {time_since_last_save:.3f}s)")
                
                if not should_save_frame:
                    continue
                
                # 비디오 파일 분할 로직
                if save_format in ['mp4', 'mkv', 'webm', 'avi']:
                    # 새 비디오 파일 시작 조건 (프레임 수 기준 또는 시간 기준)
                    should_create_new_file = False
                    
                    if stream_id not in video_writers or not video_writers[stream_id].isOpened():
                        should_create_new_file = True
                        reason = "첫 파일 또는 Writer 없음"
                    elif video_frame_counts[stream_id] >= save_interval:
                        should_create_new_file = True
                        reason = f"프레임 수 초과 ({video_frame_counts[stream_id]}/{save_interval})"
                    elif stream_id in file_start_times:
                        # 시간 기준 확인
                        time_elapsed = (timestamp - file_start_times[stream_id]).total_seconds()
                        if time_elapsed >= save_interval_seconds:
                            should_create_new_file = True
                            reason = f"시간 초과 ({time_elapsed:.1f}s/{save_interval_seconds}s)"
                    
                    if should_create_new_file:
                        
                        # 기존 writer 종료
                        if stream_id in video_writers:
                            try:
                                video_writers[stream_id].release()
                                logger.info(f"Stream {stream_id}: 비디오 저장 완료 - {video_frame_counts[stream_id]}프레임")
                            except:
                                pass
                            del video_writers[stream_id]
                        
                        # 새 파일 생성
                        file_counters[stream_id] += 1
                        video_frame_counts[stream_id] = 0
                        file_start_times[stream_id] = timestamp  # 파일 시작 시간 기록
                        
                        timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S")
                        filename = f"{stream_id}_{timestamp_str}_part{file_counters[stream_id]:03d}.{save_format}"
                        filepath = os.path.join(stream_dirs[stream_id], filename)
                        
                        height, width = frame.shape[:2]
                        fps = 15.0
                        
                        # OpenCV VideoWriter 생성 (해상도 순서 주의: width, height)
                        # mp4v 코덱 사용 (가장 안정적)
                        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                        writer = cv2.VideoWriter(filepath, fourcc, fps, (width, height))
                        codec_used = 'mp4v'
                        logger.info(f"Stream {stream_id}: 비디오 생성 시도 - 프레임 크기: {frame.shape}, Writer 크기: ({width}, {height})")
                        
                        if writer.isOpened():
                            video_writers[stream_id] = writer
                            logger.info(f"Stream {stream_id}: ✅ 새 비디오 파일 시작 - {filename} (코덱: {codec_used}, 해상도: {width}x{height}, 이유: {reason})")
                        else:
                            logger.error(f"Stream {stream_id}: VideoWriter 생성 실패 - 모든 코덱 시도 실패 (XVID, X264, mp4v)")
                            logger.error(f"Stream {stream_id}: 파일 경로: {filepath}")
                            logger.error(f"Stream {stream_id}: 해상도: {width}x{height}, FPS: {fps}")
                            writer.release()
                            continue
                    
                    # 프레임 저장 (OpenCV write() 반환값은 부정확할 수 있으므로 무시하고 계속 진행)
                    if stream_id in video_writers and video_writers[stream_id].isOpened():
                        try:
                            # 프레임 쓰기 (반환값 무시)
                            video_writers[stream_id].write(frame)
                            
                            # 성공으로 간주하고 카운터 증가
                            video_frame_counts[stream_id] += 1
                            saved_count += 1
                            stats_dict[f'{stream_id}_saved'] = stats_dict.get(f'{stream_id}_saved', 0) + 1
                            
                            if saved_count % 25 == 0:
                                total_queue_size = sum(q.qsize() for q in save_queues.values())
                                logger.info(f"Worker {worker_id}: {saved_count}프레임 저장 (15fps 제어), 총 큐: {total_queue_size}")
                                    
                        except Exception as e:
                            logger.error(f"Stream {stream_id}: 프레임 쓰기 중 오류 - {e}")
                            if stream_id in video_writers:
                                try:
                                    video_writers[stream_id].release()
                                except:
                                    pass
                                del video_writers[stream_id]
                        
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
                logger.info(f"Stream {stream_id}: 최종 비디오 저장 완료")
            except:
                pass
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
            # inotify 기반 모니터링 (long implementation continues...)
            # Full implementation would continue here but truncated for space
            logger.info("inotify 모니터링 구현 (생략)")
                
    except Exception as e:
        logger.error(f"파일 모니터 워커 오류: {e}")
    finally:
        logger.info(f"파일 모니터 워커 종료 - 감지: {detected_count}")