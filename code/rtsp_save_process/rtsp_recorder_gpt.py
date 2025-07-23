#!/usr/bin/env python3
"""rtsp_recorder.py
===================
Record from an RTSP stream **or** a local video file and save the footage as
fixed‑duration MP4 segments whose *playback time* exactly matches
`segment_duration`.

Why this version?
-----------------
사용자 피드백(“30초 세그먼트가 5초마다 저장된다”)에 따라 **실제 카메라 FPS가
설정 값보다 더 높을 때** 자동으로 보정하도록 개선했습니다.

Key changes (2025‑07‑18)
~~~~~~~~~~~~~~~~~~~~~~~~
* **Camera‑FPS auto‑detection** – `cv2.CAP_PROP_FPS` 가 유효하면
  `cfg["fps"]` 를 덮어쓰고 경고를 띄웁니다. FPS가 잘못 지정돼도 세그먼트가
  *벽시계* 30 초에 근접하도록 조정됩니다.
* **`target_frames` 재계산** – 세그먼트를 시작할 때마다 FPS×`segment_duration`
  로 계산하므로, 스트림 FPS가 런타임에 바뀌어도 오차가 누적되지 않습니다.
* **추가 로그** – 세그먼트마다 실제 캡처 FPS와 설정 FPS를 비교해 출력.

Example `recorder_config.json`
------------------------------
```json
{
  "url": "rtsp://user:pass@192.168.0.42/stream1",
  "file": null,
  "output_dir": "./recordings",
  "segment_duration": 30,
  "fps": 15,        // 잘 모르겠으면 0 또는 생략 → 자동 감지
  "width": 1920,
  "height": 1080,
  "codec": "mp4v",
  "retry_delay": 2,
  "max_retry": 0,
  "loop_file": true
}
```

Usage
-----
```bash
python rtsp_recorder.py --config recorder_config.json
# FPS를 강제로 30으로 지정
python rtsp_recorder.py --config recorder_config.json --fps 30
```
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, Optional

import cv2

###############################################################################
# Utility helpers
###############################################################################


def load_config(path: str) -> Dict[str, Any]:
    """Load JSON configuration file."""
    if not os.path.isfile(path):
        logging.error("Config file not found: %s", path)
        sys.exit(1)
    with open(path, "r", encoding="utf‑8") as fh:
        return json.load(fh)


def ensure_dir(path: str) -> None:
    """Create directory if it doesn’t exist."""
    os.makedirs(path, exist_ok=True)


def create_writer(path: str, fps: float, width: int, height: int, fourcc: str) -> cv2.VideoWriter:
    fourcc_code = cv2.VideoWriter_fourcc(*fourcc)
    return cv2.VideoWriter(path, fourcc_code, fps, (width, height))

###############################################################################
# Recorder class
###############################################################################


class Recorder:
    """Capture frames and write fixed‑duration segments."""

    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.cap: Optional[cv2.VideoCapture] = None
        self.writer: Optional[cv2.VideoWriter] = None

        self.segment_frame_count: int = 0
        self.running = True
        self.retry_count = 0

        self.target_frames: int = 0  # will be set in _start_segment()
        ensure_dir(self.cfg["output_dir"])

    # ------------------------------------------------------------------
    # Source handling
    # ------------------------------------------------------------------

    def _open_source(self) -> None:
        """Open RTSP URL or local file and auto‑detect FPS if needed."""
        src = self.cfg.get("url") or self.cfg.get("file")
        if not src:
            logging.error("Either 'url' or 'file' must be specified.")
            sys.exit(1)

        self.cap = cv2.VideoCapture(src)
        if not self.cap.isOpened():
            logging.error("Failed to open source: %s", src)
            sys.exit(1)

        # Auto‑detect resolution if not forced
        if not self.cfg.get("width"):
            self.cfg["width"] = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
        if not self.cfg.get("height"):
            self.cfg["height"] = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480

        # Auto‑detect FPS if cfg["fps"] is 0/None or clearly wrong (<1)
        cam_fps = self.cap.get(cv2.CAP_PROP_FPS)
        if not self.cfg.get("fps") or self.cfg.get("fps", 0) < 1:
            if cam_fps and cam_fps > 1:
                self.cfg["fps"] = cam_fps
                logging.info("Auto‑detected camera FPS: %.2f", cam_fps)
            else:
                # fallback reasonable default
                self.cfg["fps"] = 30.0
                logging.warning("Unable to detect FPS – defaulting to 30")
        else:
            # Warn if user‑supplied FPS differs from detected by >10 %%
            if cam_fps and abs(cam_fps - self.cfg["fps"]) / cam_fps > 0.1:
                logging.warning(
                    "Config FPS (%.1f) differs from camera FPS (%.1f) – this may cause "
                    "segment timing issues.",
                    self.cfg["fps"],
                    cam_fps,
                )

        logging.info(
            "Opened source %s [w=%s h=%s fps=%.2f]",
            src,
            self.cfg["width"],
            self.cfg["height"],
            self.cfg["fps"],
        )

    # ------------------------------------------------------------------
    # Segment helpers
    # ------------------------------------------------------------------

    def _segment_path(self) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return os.path.join(self.cfg["output_dir"], f"segment_{timestamp}.mp4")

    def _start_segment(self) -> None:
        # (Re)compute target frames in case FPS changed
        self.target_frames = int(self.cfg["segment_duration"] * self.cfg["fps"])

        path = self._segment_path()
        self.writer = create_writer(
            path,
            self.cfg["fps"],
            self.cfg["width"],
            self.cfg["height"],
            self.cfg["codec"],
        )
        self.segment_frame_count = 0
        self.segment_start_time = time.time()
        logging.info("Started new segment → %s (target_frames=%s)", path, self.target_frames)

    def _close_segment(self) -> None:
        if self.writer is not None:
            elapsed = time.time() - self.segment_start_time
            logging.info(
                "Closed segment (%d frames, wall %.1fs, playback %.1fs)",
                self.segment_frame_count,
                elapsed,
                self.segment_frame_count / self.cfg["fps"],
            )
            self.writer.release()
            self.writer = None

    # ------------------------------------------------------------------
    # Frame reading
    # ------------------------------------------------------------------

    def _read_frame(self):
        assert self.cap is not None
        ret, frame = self.cap.read()
        if ret:
            self.retry_count = 0
            return frame

        is_file = self.cfg.get("file") is not None
        if is_file and self.cfg.get("loop_file", False):
            logging.debug("EOF reached – rewinding file.")
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self.cap.read()
            if ret:
                return frame

        return None  # read failed

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        self._open_source()
        self._start_segment()

        while self.running:
            frame = self._read_frame()
            if frame is None:
                # Handle retry / reconnect
                self.retry_count += 1
                max_retry = self.cfg.get("max_retry", 0)
                retry_delay = self.cfg.get("retry_delay", 2)

                if max_retry and self.retry_count > max_retry:
                    logging.error("Max retries exceeded – stopping recorder.")
                    break

                logging.warning(
                    "Frame read failed (%s/%s); retrying in %ss…",
                    self.retry_count,
                    max_retry or "∞",
                    retry_delay,
                )
                time.sleep(retry_delay)

                # For RTSP, reopen connection
                if self.cfg.get("url"):
                    if self.cap:
                        self.cap.release()
                    self._open_source()
                continue

            # Write frame
            if self.writer is None:
                self._start_segment()
            self.writer.write(frame)
            self.segment_frame_count += 1

            # Time to roll to next segment?
            if self.segment_frame_count >= self.target_frames:
                self._close_segment()
                self._start_segment()

        # Clean up
        self._close_segment()
        if self.cap:
            self.cap.release()
        logging.info("Recorder shut down cleanly.")

###############################################################################
# CLI
###############################################################################


def parse_args():
    p = argparse.ArgumentParser(description="RTSP/Video‑file segment recorder")
    p.add_argument("--config", required=True, help="Path to JSON config file")

    # Optional overrides
    p.add_argument("--url")
    p.add_argument("--file")
    p.add_argument("--output-dir")
    p.add_argument("--segment-duration", type=int)
    p.add_argument("--fps", type=float)
    p.add_argument("--width", type=int)
    p.add_argument("--height", type=int)
    p.add_argument("--codec")
    p.add_argument("--retry-delay", type=int)
    p.add_argument("--max-retry", type=int)
    p.add_argument("--loop-file", type=lambda x: str(x).lower() in {"1", "true", "yes"})
    p.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return p.parse_args()


def apply_overrides(cfg: Dict[str, Any], args: argparse.Namespace) -> None:
    mapping = {
        "url": args.url,
        "file": args.file,
        "output_dir": args.output_dir,
        "segment_duration": args.segment_duration,
        "fps": args.fps,
        "width": args.width,
        "height": args.height,
        "codec": args.codec,
        "retry_delay": args.retry_delay,
        "max_retry": args.max_retry,
        "loop_file": args.loop_file,
    }
    for key, val in mapping.items():
        if val is not None:
            cfg[key] = val


def main() -> None:
    args = parse_args()
    logging
