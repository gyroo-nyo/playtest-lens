"""Time-stamped buffers: the dashcam memory."""
import threading
from collections import deque


class Ring:
    """Keeps (host_ts, item) for the last `seconds`."""

    def __init__(self, seconds):
        self.seconds = seconds
        self.items = deque()
        self.lock = threading.Lock()

    def add(self, ts, item):
        with self.lock:
            self.items.append((ts, item))
            while self.items and self.items[0][0] < ts - self.seconds:
                self.items.popleft()

    def window(self, t0, t1):
        with self.lock:
            return [(ts, it) for ts, it in self.items if t0 <= ts <= t1]


def segments_for(segments, t0, t1):
    """Video segments [(path, start, end)] that overlap [t0, t1], oldest first."""
    return sorted((s for s in segments if s[2] >= t0 and s[1] <= t1), key=lambda s: s[1])
