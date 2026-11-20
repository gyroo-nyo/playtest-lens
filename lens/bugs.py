"""One folder per bug: clip, logs, touches, metadata and a report a tester can paste."""
import json
import subprocess
import time
from pathlib import Path

from .logcat import headline

KIND_LABEL = {'crash': 'Crash', 'anr': 'App not responding', 'manual': 'Bug',
              'freeze': 'Freeze'}
SEEN = ('freeze',)   # caught from the screen and taps, not the log


def title(ev):
    if ev.kind == 'manual':
        return ev.note or 'Marked by tester'
    if ev.kind in SEEN:
        return ev.note or (ev.lines[0] if ev.lines else KIND_LABEL[ev.kind])
    return headline(ev.lines) or KIND_LABEL[ev.kind]


def stamp(ts):
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))


STEPS = 5          # the last taps before the mark, each shown as a picture


def step_taps(touches, t0):
    """The last few finger-downs inside the clip, as (seconds into the clip, tap)."""
    return [(ts - t0, t) for ts, t in touches if t['type'] == 'down' and ts >= t0][-STEPS:]


def step_images(folder, touches, t0):
    """step1.jpg… : the clip's frame at each tap, with a red box on the spot, so a developer sees
    what was tapped instead of reading "66% across". Returns how many were made."""
    clip, made = Path(folder) / 'clip.mp4', 0
    for i, (at, t) in enumerate(step_taps(touches, t0), 1):
        box = (f"drawbox=x=iw*{t['x']:.4f}-iw*0.05:y=ih*{t['y']:.4f}-iw*0.05:w=iw*0.1:h=iw*0.1:color=red@0.95:t=10,"
               "scale='min(960,iw)':-2")
        ok = subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'fatal', '-y', '-ss', f'{at + 0.15:.2f}', '-i', str(clip),
                             '-frames:v', '1', '-vf', box, '-q:v', '4', str(Path(folder) / f'step{i}.jpg')]).returncode == 0
        made += ok
    return made


def report(ev, meta, touches, folder=None, t0=None, clip_seconds=None):
    """Markdown report. Phase 3 adds steps a local model writes from the on-screen labels."""
    folder = Path(folder) if folder else None
    taps = step_taps(touches, t0) if t0 is not None else []
    lines = []
    for i, (at, t) in enumerate(taps, 1):
        before = ev.ts - (t0 + at)
        line = f"{i}. Tap the spot in the red box ({before:.0f} s before the bug)"
        if folder and (folder / f'step{i}.jpg').exists():
            line += f"\n\n   ![step {i}](step{i}.jpg)\n"
        lines.append(line)
    steps = '\n'.join(lines) or '1. (no taps recorded: watch clip.mp4)'
    if ev.kind == 'manual':
        actual = ev.note or '_Describe what went wrong (see clip.mp4)._'
        expected = '_What should have happened?_'
    elif ev.kind in SEEN:
        actual = (ev.lines[0] if ev.lines else KIND_LABEL[ev.kind]) + (f'. Tester: {ev.note}' if ev.note else '')
        expected = 'The game reacts to every tap.'
    else:
        actual = ev.note or (f'The game {"crashed" if ev.kind == "crash" else "stopped responding"}: `{title(ev)}`')
        expected = 'The game keeps running normally.'
    length = f'{clip_seconds:.0f} s' if clip_seconds else 'the moments'
    return f"""# [{KIND_LABEL[ev.kind]}] {title(ev)}

| | |
|---|---|
| When | {stamp(ev.ts)} |
| Device | {meta['model']} (Android {meta['android']}) |
| Game | {meta['package']} {meta['game_version']} |

## What happened
{actual}

**Watch `clip.mp4`**: {length} leading up to the bug. White dots show where the tester's finger touched.

## Expected
{expected}

## Steps (the last taps before the bug)
{steps}

## Attachments
- `clip.mp4`, `step*.jpg`{chr(10) + '- `full.mp4`: the 30 s before, in case the moment came earlier' if folder and (folder / 'full.mp4').exists() else ''}
- `logcat.txt` (device log), `touches.jsonl` (raw taps)
"""


def write(root, ev, meta, logs, touches, make_clip, t0=None, clip_seconds=None):
    """Writes the bug folder; `make_clip(path)` cuts the video. Returns the folder."""
    folder = Path(root) / f"{time.strftime('%Y%m%d-%H%M%S', time.localtime(ev.ts))}_{ev.kind}"
    folder.mkdir(parents=True, exist_ok=True)
    has_clip = make_clip(folder / 'clip.mp4')
    if has_clip and t0 is not None:
        step_images(folder, touches, t0)
    (folder / 'logcat.txt').write_text('\n'.join(line for _, line in logs) + '\n')
    (folder / 'touches.jsonl').write_text(''.join(json.dumps({'host_ts': round(ts, 3), **t}) + '\n' for ts, t in touches))
    update(folder, ev, meta, touches, has_clip, t0, clip_seconds)
    return folder


def update(folder, ev, meta, touches, has_clip=True, t0=None, clip_seconds=None):
    """(Re)writes meta and report, e.g. when the tester's note arrives after the clip."""
    folder = Path(folder)
    (folder / 'meta.json').write_text(json.dumps({**meta, 'kind': ev.kind, 'time': stamp(ev.ts), 'title': title(ev),
                                                  'note': ev.note, 'matched_lines': ev.lines, 'clip': has_clip,
                                                  'clip_start': t0, 'clip_seconds': clip_seconds}, indent=2))
    (folder / 'report.md').write_text(report(ev, meta, touches, folder, t0, clip_seconds))
