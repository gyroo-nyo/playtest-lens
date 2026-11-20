"""Freeze detection: the screen stops changing AND the game stops drawing frames.

Video alone can't tell a freeze from a still screen (GFL's pre-snap, a menu): both look the same.
So a freeze needs the game's own frame rate too. Android logs it for the game's surface
(`BufferQueueProducer ... SurfaceView[<package>...] queueBuffer: fps=46.3`, about once a second
while it draws). A frozen game stops drawing, so those lines stop or drop to ~0.

Lens reports only when all of this holds:
- 3+ taps (the tester is trying to play),
- the whole screen stays the same for STILL_FOR seconds (Show-taps dots ignored),
- the game drew under DRAWING fps over that time (or stopped logging frames at all).
Phones that never log the frame rate get no automatic freeze reports: better none than wrong ones.
Stuck buttons are not detected: a tap on a dead spot and a tap on a broken button look the same.
"""
import re
from collections import deque

from .logcat import Event

W, H = 160, 90
STILL = 1.0        # mean pixel change (0..255) below this: the screen did not change
STILL_FOR = 3.0    # seconds the whole screen must stay the same
TAPS = 3           # taps during that time
DOT = 9            # pixels ignored around each touch (the Show-taps dot)
DRAWING = 2.0      # game frame rate at or above this: the game is still drawing, not frozen
COOLDOWN = 10.0    # one bug per freeze, not one per tap


def game_frames(msg, package):
    """(fps, longest frame in ms) from a BufferQueueProducer line for the game's own surface, else None."""
    if f'[{package}' not in msg or 'queueBuffer: fps=' not in msg:
        return None
    m = re.search(r'queueBuffer: fps=([\d.]+).*?max=([\d.]+)', msg)
    return (float(m.group(1)), float(m.group(2))) if m else None


def game_fps(msg, package):
    """Frame rate from a BufferQueueProducer line for the game's own surface, else None."""
    f = game_frames(msg, package)
    return f[0] if f else None


def change(a, b, holes):
    """Mean absolute difference of two frames, skipping pixels near `holes` [(x, y) in 0..1]."""
    holes = [(x * W, y * H) for x, y in holes]
    total = n = 0
    for row in range(0, H, 2):              # every other pixel: plenty for "did it move"
        for col in range(0, W, 2):
            if any((col - hx) ** 2 + (row - hy) ** 2 < DOT * DOT for hx, hy in holes):
                continue
            i = row * W + col
            total += abs(a[i] - b[i])
            n += 1
    return total / n if n else 0.0


class Detector:
    def __init__(self):
        self.frames = deque()     # (ts, bytes), last few seconds
        self.touches = deque()    # (ts, type, x, y)
        self.quiet_until = 0.0
        self.fps = deque()        # (ts, fps) of the game's surface
        self.logs_fps = False     # has this phone ever logged the game's frame rate?

    def drawing(self, ts, fps):
        self.logs_fps = True
        self.fps.append((ts, fps))
        while self.fps and self.fps[0][0] < ts - 20:
            self.fps.popleft()

    def touch(self, ts, t):
        self.touches.append((ts, t['type'], t['x'], t['y']))
        while self.touches and self.touches[0][0] < ts - 10:
            self.touches.popleft()

    def frame(self, ts, data):
        """Feed one frame; returns an Event('freeze') or None."""
        if len(data) != W * H:
            return None
        self.frames.append((ts, data))
        while self.frames and self.frames[0][0] < ts - STILL_FOR - 3:
            self.frames.popleft()
        if ts < self.quiet_until:
            return None
        downs = [(t, x, y) for t, kind, x, y in self.touches if kind == 'down' and ts - STILL_FOR - 1 <= t <= ts - 0.6]
        if len(downs) < TAPS:
            return None
        first = downs[0][0]
        if ts - first < STILL_FOR:
            return None
        before = self.at(first - 0.1)
        if before is None:
            return None
        holes = [(x, y) for t, _, x, y in self.touches if t >= first - 0.6]
        since = [f for t, f in self.frames if t >= first]
        if len(since) < 5 or any(change(before, f, holes) >= STILL for f in since):
            return None                     # something moved: the game is alive
        if not self.logs_fps:
            return None                     # can't confirm the game stopped drawing
        if any(f >= DRAWING for t, f in self.fps if t >= first):
            return None                     # still drawing: a still screen, not a freeze
        return self.caught('freeze', first, f'The game froze: {len(downs)} taps in {ts - first:.0f} s, '
                                            f'nothing on screen changed and the game stopped drawing frames')

    def at(self, ts):
        """The last frame at or before `ts`."""
        best = None
        for t, f in self.frames:
            if t > ts:
                break
            best = f
        return best

    def caught(self, kind, ts, what):
        self.quiet_until = ts + COOLDOWN
        return Event(kind, ts, lines=[what])
