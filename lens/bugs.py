"""One folder per bug: clip, logs, touches, metadata and a report a tester can paste."""
import json
import time
from pathlib import Path

from .logcat import headline

KIND_LABEL = {'crash': 'Crash', 'anr': 'App not responding', 'manual': 'Bug'}


def title(ev):
    if ev.kind == 'manual':
        return ev.note or 'Marked by tester'
    return headline(ev.lines) or KIND_LABEL[ev.kind]


def stamp(ts):
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))


def report(ev, meta, touches):
    """Markdown report. Phase 3 replaces the steps with ones a local model writes."""
    downs = [t for _, t in touches if t['type'] == 'down'][-8:]
    steps = '\n'.join(f"{i}. Tap at {t['x'] * 100:.0f}% across, {t['y'] * 100:.0f}% down" for i, t in enumerate(downs, 1)) \
        or '1. (no touches recorded)'
    actual = ev.note or (f'The game {"crashed" if ev.kind == "crash" else "stopped responding"}: `{title(ev)}`')
    return f"""# [{KIND_LABEL[ev.kind]}] {title(ev)}

| | |
|---|---|
| When | {stamp(ev.ts)} |
| Device | {meta['model']} (Android {meta['android']}) |
| Game | {meta['package']} {meta['game_version']} |

## Steps to reproduce
{steps}

## Actual result
{actual}

## Expected result
The game keeps running normally.

## Attachments
- `clip.mp4`: 20 s before to 5 s after
- `logcat.txt`, `touches.jsonl`
"""


def write(root, ev, meta, logs, touches, make_clip):
    """Writes the bug folder; `make_clip(path)` cuts the video. Returns the folder."""
    folder = Path(root) / f"{time.strftime('%Y%m%d-%H%M%S', time.localtime(ev.ts))}_{ev.kind}"
    folder.mkdir(parents=True, exist_ok=True)
    has_clip = make_clip(folder / 'clip.mp4')
    (folder / 'logcat.txt').write_text('\n'.join(line for _, line in logs) + '\n')
    (folder / 'touches.jsonl').write_text(''.join(json.dumps({'host_ts': round(ts, 3), **t}) + '\n' for ts, t in touches))
    update(folder, ev, meta, touches, has_clip)
    return folder


def update(folder, ev, meta, touches, has_clip=True):
    """(Re)writes meta and report, e.g. when the tester's note arrives after the clip."""
    folder = Path(folder)
    (folder / 'meta.json').write_text(json.dumps({**meta, 'kind': ev.kind, 'time': stamp(ev.ts), 'title': title(ev),
                                                  'note': ev.note, 'matched_lines': ev.lines, 'clip': has_clip}, indent=2))
    (folder / 'report.md').write_text(report(ev, meta, touches))
