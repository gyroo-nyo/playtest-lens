"""Turn `adb shell getevent -lt <device>` lines into touch down / move / up in screen space."""
import re

LINE = re.compile(r'^\[\s*([\d.]+)\]\s+(\w+)\s+(\w+)\s+(\w+)')


def to_screen(nx, ny, rotation):
    """Panel coordinates (0..1, natural orientation) to the screen as shown (0..1)."""
    return [(nx, ny), (ny, 1 - nx), (1 - nx, 1 - ny), (1 - ny, nx)][rotation % 4]


class Tracker:
    """Follows the first finger only.
    shortcut: multi-touch (pinch, two-thumb) is reduced to the first contact; upgrade for replay in phase 4."""

    def __init__(self, max_x, max_y, rotation=0):
        self.max_x, self.max_y, self.rotation = max_x, max_y, rotation
        self.x = self.y = None
        self.down = False
        self.pending = None
        self.slot = 0

    def feed(self, line):
        """Returns {'t': kernel seconds, 'type': down|move|up, 'x', 'y'} on SYN_REPORT, else None."""
        m = LINE.match(line)
        if not m:
            return None
        t, _ev, code, value = m.groups()
        if code == 'ABS_MT_SLOT':
            self.slot = int(value, 16)
        if self.slot != 0:
            return None
        if code == 'ABS_MT_POSITION_X':
            self.x = int(value, 16)
            self.pending = self.pending or 'move'
        elif code == 'ABS_MT_POSITION_Y':
            self.y = int(value, 16)
            self.pending = self.pending or 'move'
        elif code == 'ABS_MT_TRACKING_ID':
            self.pending = 'up' if value == 'ffffffff' else 'down'
        elif code == 'SYN_REPORT' and self.pending and self.x is not None and self.y is not None:
            kind, self.pending = self.pending, None
            if kind == 'move' and not self.down:
                return None
            self.down = kind != 'up'
            sx, sy = to_screen(self.x / self.max_x, self.y / self.max_y, self.rotation)
            return {'t': float(t), 'type': kind, 'x': round(sx, 4), 'y': round(sy, 4)}
        return None
