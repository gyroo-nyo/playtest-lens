"""The FPS meter burned into clips: "47 FPS" in the top-left corner, from the game's own frame rate.

Pure Python (a tiny bitmap font written as PPM images), because Homebrew's ffmpeg has no drawtext
and Lens has no image library. ffmpeg overlays the images in sequence, one per reading.
"""
from pathlib import Path

# 5x7 bitmap font: one string per row, '#' = lit
FONT = {
    '0': ['.###.', '#...#', '#..##', '#.#.#', '##..#', '#...#', '.###.'],
    '1': ['..#..', '.##..', '..#..', '..#..', '..#..', '..#..', '.###.'],
    '2': ['.###.', '#...#', '....#', '...#.', '..#..', '.#...', '#####'],
    '3': ['####.', '....#', '....#', '.###.', '....#', '....#', '####.'],
    '4': ['...#.', '..##.', '.#.#.', '#..#.', '#####', '...#.', '...#.'],
    '5': ['#####', '#....', '####.', '....#', '....#', '#...#', '.###.'],
    '6': ['..##.', '.#...', '#....', '####.', '#...#', '#...#', '.###.'],
    '7': ['#####', '....#', '...#.', '..#..', '.#...', '.#...', '.#...'],
    '8': ['.###.', '#...#', '#...#', '.###.', '#...#', '#...#', '.###.'],
    '9': ['.###.', '#...#', '#...#', '.####', '....#', '...#.', '.##..'],
    'F': ['#####', '#....', '#....', '####.', '#....', '#....', '#....'],
    'P': ['####.', '#...#', '#...#', '####.', '#....', '#....', '#....'],
    'S': ['.####', '#....', '#....', '.###.', '....#', '....#', '####.'],
    '-': ['.....', '.....', '.....', '#####', '.....', '.....', '.....'],
    ' ': ['.....'] * 7,
}
SCALE = 5           # pixels per font dot
PAD = 2             # dots of padding around the text
BG = (20, 20, 20)
STALE = 2.5         # seconds without a reading: the game isn't drawing, show "--"


def color(fps):
    if fps is None:
        return (150, 150, 150)
    return (80, 220, 100) if fps >= 40 else (240, 200, 60) if fps >= 25 else (240, 70, 60)


def label(fps):
    return f'{"--" if fps is None else min(99, round(fps)):>2} FPS'


def ppm(text, rgb):
    """The text as a binary PPM image."""
    cols = len(text) * 6 - 1 + 2 * PAD
    rows = 7 + 2 * PAD
    w, h = cols * SCALE, rows * SCALE
    px = bytearray(bytes(BG) * (w * h))
    for i, ch in enumerate(text):
        for r, line in enumerate(FONT[ch]):
            for c, dot in enumerate(line):
                if dot != '#':
                    continue
                x0, y0 = (PAD + i * 6 + c) * SCALE, (PAD + r) * SCALE
                for y in range(y0, y0 + SCALE):
                    for x in range(x0, x0 + SCALE):
                        px[(y * w + x) * 3:(y * w + x) * 3 + 3] = bytes(rgb)
    return f'P6 {w} {h} 255\n'.encode() + bytes(px)


def timeline(readings, t0, t1, step=0.5):
    """[(seconds into the clip, fps or None)] each time the meter's text changes. readings: [(host ts, fps)]."""
    readings = sorted(readings)
    out, t = [], t0
    while t < t1:
        now = [f for ts, f in readings if ts <= t and t - ts <= STALE]
        fps = now[-1] if now else None
        if not out or label(out[-1][1]) != label(fps):
            out.append((t - t0, fps))
        t += step
    return out or [(0.0, None)]


def write(readings, t0, t1, folder):
    """Writes the meter images and an ffmpeg concat list into `folder`; returns the list's path."""
    folder = Path(folder)
    steps = timeline(readings, t0, t1)
    lines, cache = [], {}
    for i, (at, fps) in enumerate(steps):
        text = label(fps)
        if text not in cache:
            cache[text] = folder / f'meter{len(cache)}.ppm'
            cache[text].write_bytes(ppm(text, color(fps)))
        end = steps[i + 1][0] if i + 1 < len(steps) else t1 - t0
        lines.append(f"file '{cache[text]}'\nduration {max(0.04, end - at):.2f}\n")
    lines.append(f"file '{cache[label(steps[-1][1])]}'\n")   # concat needs the last image twice
    listing = folder / 'meter.txt'
    listing.write_text(''.join(lines))
    return listing
