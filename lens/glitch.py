"""Visual glitches: a missing texture or shader that an engine paints solid magenta (#FF00FF).

Black screens are not checked: GFL goes black on purpose (loading, the play-calling screen, the
lock screen), so "black" would only produce false alarms. Magenta is never a design colour in a
football game, and it's what Unity, Unreal, Godot and libGDX tools show for a missing asset.
Runs on the full-size frame the text check already takes every 3 s, shrunk to W x H.
"""
import subprocess

from .logcat import Event

W, H = 64, 36
MAGENTA = 0.04     # share of the screen that must be magenta (4%: a missing texture is big and solid)


def is_magenta(r, g, b):
    return r > 200 and b > 200 and g < 70


def magenta_share(rgb):
    """Share of pixels that are missing-texture magenta, from raw RGB24 bytes."""
    n = len(rgb) // 3
    hits = sum(1 for i in range(0, n * 3, 3) if is_magenta(rgb[i], rgb[i + 1], rgb[i + 2]))
    return hits / n if n else 0.0


def small_rgb(image):
    """The image shrunk to W x H, as raw RGB24 bytes."""
    out = subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'fatal', '-i', str(image), '-vf', f'scale={W}:{H}',
                          '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], stdin=subprocess.DEVNULL, capture_output=True)
    return out.stdout if len(out.stdout) == W * H * 3 else b''


class Detector:
    def __init__(self):
        self.quiet_until = 0.0

    def check(self, ts, rgb):
        share = magenta_share(rgb)
        if share < MAGENTA or ts < self.quiet_until:
            return None
        self.quiet_until = ts + 30
        return Event('glitch', ts, lines=[f'Missing texture: {share:.0%} of the screen is solid magenta'])
