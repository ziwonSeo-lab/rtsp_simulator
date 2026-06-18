## 1. start mediamtx

### 실행경로 
pwd : /home/szw001/development/2025/IUU/rtsp_simulator/code/multi_rtspsender/scripts/management$ 
### 1.1기존에 mediamtx 실행 하지 않고있을 때
cmd : bash start_all_mediamtx.sh 
### 1.2기존에 mediamtx 실행중일 때
cmd : bash stop_all_mediamtx.sh 
>> mediamtx 각각 종료 확인
cmd : bash start_all_mediamtx.sh
>> 각각 실행확인


## 2. start rtsp sender
pwd : /home/szw001/development/2025/IUU/rtsp_simulator/code/multi_rtspsender/
cmd : nohup sudo python3 src/server/rtsp_sender.py -c config/config_noloss.json 2>&1 &

### 2.1 rtsp_sender.py 실행확인 ( 프로세스 킬)
ps -ef | grep rtsp_sender.py
sudo kill -9 psnumber

### 데이터 흐름

데이터 흐름
비디오 파일 
  ↓ (FFmpeg concat)
RTMP → localhost:1911-1916 
  ↓ (MediaMTX 변환)
RTSP → 10.2.10.158:1111-1116

### 비디오 추가.
현재 Stream 1 (12번째 줄):
"video_files": ["/home/szw001/.../미디어1_upscaled_1920x1080.mp4"]
여러 파일 추가:
"video_files": [
  "/home/szw001/.../미디어1_upscaled_1920x1080.mp4",
  "/home/szw001/.../미디어2_upscaled_1920x1080.mp4",
  "/home/szw001/.../미디어3_upscaled_1920x1080.mp4"
]