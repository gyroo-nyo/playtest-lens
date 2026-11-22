"""Turn `adb shell getevent -lt <device>` lines into touch down / move / up in screen space."""
import re

LINE = re.compile(r'^\[\s*([\d.]+)\]\s+(\w+)\s+(\w+)\s+(\w+)')


def to_screen(nx, ny, rotation):
    """Panel coordinates (0..1, natural orientation) to the screen as shown (0..1)."""
    return [(nx, ny), (ny, 1 - nx), (1 - nx, 1 - ny), (1 - ny, nx)][rotation % 4]


class Tracker:
    """Follows every finger (multi-touch slots), so a thumb held on the joystick doesn't hide the other hand's taps."""

    def __init__(self, max_x, max_y, rotation=0):
        self.max_x, self.max_y, self.rotation = max_x, max_y, rotation
        self.slot = 0
        self.fingers = {}       # slot -> {'x', 'y', 'down', 'pending'}

    def feed(self, line):
        """Returns a list of {'t': kernel seconds, 'type': down|move|up, 'x', 'y', 'finger'} on SYN_REPORT, else []."""
        m = LINE.match(line)
        if not m:
            return []
        t, _ev, code, value = m.groups()
        if code == 'ABS_MT_SLOT':
            self.slot = int(value, 16)
            return []
        f = self.fingers.setdefault(self.slot, {'x': None, 'y': None, 'down': False, 'pending': None})
        if code == 'ABS_MT_POSITION_X':
            f['x'] = int(value, 16)
            f['pending'] = f['pending'] or 'move'
        elif code == 'ABS_MT_POSITION_Y':
            f['y'] = int(value, 16)
            f['pending'] = f['pending'] or 'move'
        elif code == 'ABS_MT_TRACKING_ID':
            f['pending'] = 'up' if value == 'ffffffff' else 'down'
        elif code == 'SYN_REPORT':
            out = []
            for slot, g in sorted(self.fingers.items()):
                kind, g['pending'] = g['pending'], None
                if not kind or g['x'] is None or g['y'] is None or (kind == 'move' and not g['down']):
                    continue
                g['down'] = kind != 'up'
                sx, sy = to_screen(g['x'] / self.max_x, g['y'] / self.max_y, self.rotation)
                out.append({'t': float(t), 'type': kind, 'x': round(sx, 4), 'y': round(sy, 4), 'finger': slot})
            return out
        return []
