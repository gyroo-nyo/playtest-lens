"""Turns raw taps into what a developer can read: "JUMP ×7, dragged the bottom-left for 6 s".

Each finger-down → up is one action: a tap, a hold or a drag. The action gets the name of the text
under the finger (read off the frame just before it with macOS Vision: JUMP, SWITCH, PLAY), or else
where on the screen it was. The situation is the text along the top of the screen at the bug (in GFL,
the scoreboard: down, clock, score).
"""
import re
import subprocess
import tempfile
from collections import OrderedDict
from pathlib import Path

from . import text

NEAR = 0.07        # a label this close to the finger (fraction of the screen) names the action
DRAG = 0.03        # moved further than this: a drag, not a tap
HOLD = 0.35        # seconds down before a still finger is a hold
TOP = 0.09         # the strip along the top that holds a scoreboard / title
SAMPLE = 4         # frames a second read for labels


def actions(touches, t0, t1=None):
    """[(start, seconds held, x, y, distance moved)] for each finger-down inside [t0, t1], in screen 0..1."""
    out, cur = [], None
    for ts, t in touches:
        if t1 is not None and ts > t1:
            break
        if t['type'] == 'down':
            if cur and cur[0] >= t0:            # a down without an up (second finger): close the last one
                out.append((cur[0], ts - cur[0], cur[1], cur[2], cur[3]))
            cur = [ts, t['x'], t['y'], 0.0, t['x'], t['y']]
        elif cur and t['type'] == 'move':
            cur[3] = max(cur[3], ((t['x'] - cur[1]) ** 2 + (t['y'] - cur[2]) ** 2) ** 0.5)
        elif cur and t['type'] == 'up':
            if cur[0] >= t0:
                out.append((cur[0], ts - cur[0], cur[1], cur[2], cur[3]))
            cur = None
    return out


def where(x, y):
    """'the bottom-left' etc."""
    row = 'top' if y < 0.33 else 'bottom' if y > 0.66 else 'middle'
    col = 'left' if x < 0.33 else 'right' if x > 0.66 else 'centre'
    return 'the centre' if (row, col) == ('middle', 'centre') else f'the {row}-{col}' if row != 'middle' else f'the {col}'


def label_at(lines, x, y):
    """The on-screen text under or next to (x, y), or None. lines: [(text, x, y, w, h)]."""
    best = None
    for words, lx, ly, lw, lh in lines:
        dx = max(lx - x, 0, x - (lx + lw))
        dy = max(ly - y, 0, y - (ly + lh))
        d = (dx * dx + dy * dy) ** 0.5
        if d <= NEAR and len(words.strip()) >= 2 and not words.strip().isdigit() and (best is None or d < best[0]):
            best = (d, words.strip())
    return best[1] if best else None


def frames(clip, folder, rate=SAMPLE):
    """Pulls `rate` frames a second out of the clip. Returns [(seconds into the clip, path)]."""
    folder = Path(folder)
    subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'fatal', '-y', '-i', str(clip), '-vf', f'fps={rate}',
                    '-q:v', '3', str(folder / 'f%04d.jpg')], stdin=subprocess.DEVNULL)
    return [((int(p.stem[1:]) - 1) / rate, p) for p in sorted(folder.glob('f*.jpg'))]


def snap(label, known):
    """A label half-covered by the finger ('SWIT', 'ISWITCH') → the full one seen elsewhere ('SWITCH')."""
    if not label:
        return label
    for full, _ in sorted(known.items(), key=lambda kv: -kv[1]):
        a, b = label.upper(), full.upper()
        cut_off = len(b) > len(a) >= 3 and b.startswith(a) and len(b) - len(a) <= 3      # 'SWIT' → 'SWITCH'
        stray = len(a) == len(b) + 1 and a.endswith(b) and known[full] > known.get(label, 0)   # 'ISWITCH' → 'SWITCH'
        if cut_off or stray:
            return full
    return label


def name(action, lines, known=None):
    start, held, x, y, moved = action
    if y < 0.04 and moved >= DRAG:
        return "pulled down the phone's notification shade", held
    label = snap(label_at(lines, x, y), known or {})
    if moved >= DRAG:
        return f'dragged {label or where(x, y)}', held
    if held >= HOLD:
        return f'held {label or where(x, y)}', held
    return label or f'tapped {where(x, y)}', held


def summary(named):
    """'JUMP ×7, SWITCH, dragged the bottom-left (6 s)' from [(name, seconds)] in order of first use."""
    groups = OrderedDict()
    for what, held in named:
        n, total = groups.get(what, (0, 0.0))
        groups[what] = (n + 1, total + held)
    parts = []
    for what, (n, total) in groups.items():
        if what.startswith(('dragged', 'held')):
            parts.append(f'{what} ({total:.0f} s)' if total >= 1 else what)
        else:
            parts.append(f'{what} ×{n}' if n > 1 else what)
    return ', '.join(parts)


def situation(lines):
    """The text along the top of the screen, left to right ('FIRST DOWN AND 10 · 1:53 Q2 · DALLAS 7 …')."""
    def game_text(t):     # scoreboard words and scores; not the phone's status bar ("* Ш kB/s", "08:57 0 0 9")
        return re.fullmatch(r"[A-Za-z0-9 :.&'!%-]+", t) and (re.search(r'[A-Za-z]', t) or re.fullmatch(r'\d{1,3}', t))
    top = sorted((l for l in lines if l[2] + l[4] / 2 < TOP), key=lambda l: l[1])
    return ' · '.join(l[0].strip() for l in top if game_text(l[0].strip()))


def describe(clip, touches, t0, moment):
    """What the tester did in the clip and what the screen showed at `moment` (seconds into the clip).
    Returns {'did': [(seconds into the clip, name)], 'summary': str, 'situation': str}."""
    binary = text.ocr_binary()
    if not binary or not Path(clip).exists():
        return None
    with tempfile.TemporaryDirectory(prefix='lens-describe-') as tmp:
        shots = frames(clip, tmp)
        if not shots:
            return None
        read = text.read_many([p for _, p in shots])
        def lines_at(at):
            """Text on the last frame before `at` (the finger and its Show-taps dot cover the label after)."""
            before = [p for t, p in shots if t <= at - 0.1] or [shots[0][1]]
            return read.get(str(before[-1]), [])
        known = {}                        # every label read in the clip, by how often: to fix half-covered ones
        for found in read.values():
            for words, *_ in found:
                known[words.strip()] = known.get(words.strip(), 0) + 1
        did = []
        for act in actions(touches, t0):
            what, held = name(act, lines_at(act[0] - t0), known)
            did.append((act[0] - t0, what, held))
        # the scoreboard can be hidden at the exact moment: use the latest frame that shows one
        sit = ''
        for t, p in sorted(shots, key=lambda tp: abs(tp[0] - moment) + (0.5 if tp[0] > moment else 0)):
            if (sit := situation(read.get(str(p), []))):
                break
    return {'did': [(at, what) for at, what, _ in did], 'summary': summary([(w, h) for _, w, h in did]), 'situation': sit}
