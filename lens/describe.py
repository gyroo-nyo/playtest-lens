"""Turns raw taps into what a developer can read: "JUMP ×7, dragged the bottom-left for 6 s".

Each finger-down → up is one action: a tap, a hold or a drag. The action gets the name of the text
under the finger (read off the frame just before it with macOS Vision: JUMP, SWITCH, PLAY), or else
where on the screen it was. The situation is the text along the top of the screen at the bug (in GFL,
the scoreboard: down, clock, score).
"""
import difflib
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
    out, cur = [], {}      # finger -> [start, x, y, moved]; old touch logs have no finger: one finger
    for ts, t in touches:
        if t1 is not None and ts > t1:
            break
        f = t.get('finger', 0)
        if t['type'] == 'down':
            if f in cur and cur[f][0] >= t0:      # a down without an up: close the last one
                out.append((cur[f][0], ts - cur[f][0], cur[f][1], cur[f][2], cur[f][3]))
            cur[f] = [ts, t['x'], t['y'], 0.0]
        elif f in cur and t['type'] == 'move':
            c = cur[f]
            c[3] = max(c[3], ((t['x'] - c[1]) ** 2 + (t['y'] - c[2]) ** 2) ** 0.5)
        elif f in cur and t['type'] == 'up':
            c = cur.pop(f)
            if c[0] >= t0:
                out.append((c[0], ts - c[0], c[1], c[2], c[3]))
    out.sort()
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
    # GFL's buttons are capitals; a lowercase or odd letter is a misread where the finger covers it ('JUr', 'JUř', 'DIVE(')
    head = re.sub(r'[^A-Z0-9 ]', '', label).strip()
    odd = head != label.strip()
    for full, _ in sorted(known.items(), key=lambda kv: -kv[1]):
        a, b = label.upper(), full.upper()
        cut_off = len(b) > len(a) >= 3 and b.startswith(a) and len(b) - len(a) <= 3      # 'SWIT' → 'SWITCH'
        stray = len(a) == len(b) + 1 and a.endswith(b) and known[full] > known.get(label, 0)   # 'ISWITCH' → 'SWITCH'
        misread = odd and (head == full or len(head) >= 2 and full.startswith(head) and len(full) - len(head) <= 3
                           and known[full] > 2 * known.get(label, 0))
        if cut_off or stray or misread:
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
    return scoreboard(' · '.join(t for l in top if not in_meter(l) and (t := no_meter(l[0])) and game_text(t)))


# GFL's play calls: on defense PREVENT / PRESSURE / BLITZ (read off the 15 fps play screen in real clips);
# on offense the team's name and a number, 'CHICAGO 1', 'CHICAGO 2' (the tester's word).
PLAYS = {'PREVENT', 'PRESSURE', 'BLITZ'}
OFFENSE = re.compile(r"[A-Z][A-Z .'-]{2,} \d{1,2}")


def play_called(names):
    """The last play call the tester tapped, from the tap names in order ('dragged BLITZ' counts), or None."""
    for what in reversed(names):
        word = re.sub(r'^(dragged|held)\s+', '', what).strip().upper()
        if word in PLAYS or OFFENSE.fullmatch(word):
            return word
    return None


ORDINAL = {'FIRST': '1st', 'SECOND': '2nd', 'THIRD': '3rd', 'FOURTH': '4th'}


def scoreboard(raw):
    """Only the parts of the scoreboard OCR read reliably: '2nd & 10 · 0:15 Q3 · CHICAGO 21 – NEW ENGLAND 14'.
    '' when it shows neither the down nor the clock (a menu, an ad, or OCR junk like '1E22').
    Safe to run on its own output, so old saved readings can be cleaned the same way."""
    out = []
    if m := re.search(r'(?<!\S)(1st|2nd|3rd|4th|\?) & (\d{1,2}|GOAL)(?!\S)', raw):    # already cleaned
        out.append(f'{m[1]} & {m[2]}')
    elif m := re.search(r'(?:([A-Z]+)\s+)?D?OWN AND (\w+)', raw, re.I):
        word = difflib.get_close_matches((m[1] or '').upper(), ORDINAL, n=1, cutoff=0.6)   # 'FIROT' -> FIRST
        dist = m[2].upper() if re.fullmatch(r'\d{1,2}|GOAL', m[2], re.I) else '?'
        if word or dist != '?':
            out.append(f"{ORDINAL[word[0]] if word else '?'} & {dist}")
    clock = re.search(r'\b(\d{1,2}:\d\d)\s*·?\s*(Q[1-4]|OT)\b', raw)
    if clock:
        out.append(f'{clock[1]} {clock[2]}')
        teams, name = [], []
        for tok in re.findall(r"[A-Z][A-Z.'&-]*|\d{1,3}", raw[clock.end():]):
            if tok.isdigit():
                if name:
                    teams.append(f"{' '.join(name)} {tok}"); name = []
            else:
                name.append(tok)
                continue
        if name:
            teams.append(' '.join(name))
        teams = [t for t in teams if len(re.sub(r'[\d ]', '', t)) >= 5][:2]      # team names, not scraps like 'LERR'
        if teams:
            out.append(' – '.join(teams))
    return ' · '.join(out) if out else ''


# Lens's FPS meter: 195 x 55 px at (24, 24) in clips about 2400 x 1080 (meter.py, video.py). Text read wholly
# inside it is the meter however OCR spells it ('f60 FPSS', '160 FFS'); text running on past it is the scoreboard.
METER_BOX = (0.1, 0.085)


def in_meter(line):
    _, x, y, w, h = line
    return x + w < METER_BOX[0] and y + h < METER_BOX[1]


METER = re.compile(r'^\W*[a-z]?(\d{1,3}|--)\s*F[PF]?[S5]*', re.I)


def no_meter(text):
    """The text without Lens's FPS meter run into it ('59 FPSOWN AND 10' -> 'OWN AND 10'); '' if only a scrap is left."""
    text = text.strip()
    rest = METER.sub('', text).strip()
    return text if rest == text else rest if len(rest) >= 4 else ''


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
        if play := play_called([w for _, w, _ in did]):
            sit = f'{sit} · play called: {play}' if sit else f'play called: {play}'
    return {'did': [(at, what) for at, what, _ in did], 'summary': summary([(w, h) for _, w, h in did]), 'situation': sit}
