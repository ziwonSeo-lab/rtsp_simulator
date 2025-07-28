#!/bin/bash

echo "MediaMTX 인스턴스들을 종료합니다..."
if pgrep -f mediamtx > /dev/null; then
    pkill -f mediamtx
    sleep 3
    if pgrep -f mediamtx > /dev/null; then
        pkill -9 -f mediamtx
        echo "강제 종료되었습니다."
    else
        echo "정상 종료되었습니다."
    fi
else
    echo "실행 중인 MediaMTX 인스턴스가 없습니다."
fi
