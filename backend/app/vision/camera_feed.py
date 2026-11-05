"""In-memory Camera Feed and Frame Buffer Manager.

Strictly keeps only the latest decoded frame in RAM for real-time vision processing.
Zero disk I/O: no video or raw frame is ever saved to disk.
"""
import time
from typing import Optional
import cv2
import numpy as np


class CameraFeedManager:
    """Manages the in-memory camera buffer, FPS measurement, and decoded OpenCV frames."""

    MAX_FRAME_BYTES = 4 * 1024 * 1024
    MAX_FRAME_SIDE = 4096
    MAX_FRAME_PIXELS = 12_000_000

    def __init__(self):
        self.latest_frame: Optional[np.ndarray] = None
        self.latest_jpeg: Optional[bytes] = None
        self.frame_count: int = 0
        self.fps: float = 0.0
        self.last_frame_time: Optional[float] = None
        self.active_device_id: Optional[str] = None
        self._fps_window = []

    def process_frame_bytes(self, device_id: str, raw_bytes: bytes) -> bool:
        """Decode incoming JPEG bytes using OpenCV and store strictly in RAM."""
        if not raw_bytes or len(raw_bytes) > self.MAX_FRAME_BYTES:
            return False

        if not isinstance(device_id, str) or not device_id or len(device_id) > 50:
            return False

        np_arr = np.frombuffer(raw_bytes, dtype=np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if frame is None:
            return False
        height, width = frame.shape[:2]
        if min(width, height) < 32 or max(width, height) > self.MAX_FRAME_SIDE:
            return False
        if width * height > self.MAX_FRAME_PIXELS:
            return False

        now = time.time()
        self.latest_frame = frame
        self.latest_jpeg = raw_bytes
        self.active_device_id = device_id
        self.frame_count += 1

        # Moving window for FPS calculation (last 2 seconds)
        self._fps_window.append(now)
        self._fps_window = [t for t in self._fps_window if now - t <= 2.0]
        if len(self._fps_window) > 1:
            duration = self._fps_window[-1] - self._fps_window[0]
            if duration > 0:
                self.fps = round((len(self._fps_window) - 1) / duration, 1)
        else:
            self.fps = 1.0

        self.last_frame_time = now
        return True

    def get_latest_frame(self) -> Optional[np.ndarray]:
        """Returns the latest OpenCV BGR frame (numpy array)."""
        return self.latest_frame

    def get_latest_jpeg(self) -> Optional[bytes]:
        """Returns the latest raw JPEG bytes for admin live preview."""
        return self.latest_jpeg

    def is_active(self, timeout_seconds: float = 10.0) -> bool:
        """Check whether camera has sent a frame within the last timeout_seconds."""
        if self.last_frame_time is None:
            return False
        return (time.time() - self.last_frame_time) <= timeout_seconds

    def get_stats(self) -> dict:
        """Returns feed telemetry (FPS, frame count, active device)."""
        is_live = self.is_active(timeout_seconds=10.0)
        return {
            "has_frame": self.latest_frame is not None,
            "device_id": self.active_device_id,
            "frame_count": self.frame_count,
            "fps": self.fps if is_live else 0.0,
            "is_live": is_live,
            "last_frame_time": self.last_frame_time,
            "resolution": (
                f"{self.latest_frame.shape[1]}x{self.latest_frame.shape[0]}"
                if self.latest_frame is not None
                else None
            ),
        }

    def clear(self):
        """Clear memory buffer."""
        self.latest_frame = None
        self.latest_jpeg = None
        self.frame_count = 0
        self.fps = 0.0
        self.last_frame_time = None
        self.active_device_id = None
        self._fps_window = []


camera_feed = CameraFeedManager()
