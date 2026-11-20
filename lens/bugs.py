"""One folder per bug: clip, logs, touches, metadata and a report a tester can paste."""
import json
import subprocess
import time
from pathlib import Path

from .logcat import headline

KIND_LABEL = {'crash': 'Crash', 'anr': 'App not responding', 'manual': 'Bug',
              'freeze': 'Freeze', 'lag': 'Frame drops', 'text': 'Text bug', 'glitch': 'Visual glitch'}
SEEN = ('freeze', 'lag', 'text', 'glitch')   # caught from the screen and taps, not the log


def title(ev):
    if ev.kind == 'manual':
        return ev.note or 'Marked by tester'
    if ev.kind in SEEN:
        return ev.note or (ev.lines[0] if ev.lines else KIND_LABEL[ev.kind])
    return headline(ev.lines) or KIND_LABEL[ev.kind]


def stamp(ts):
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))


def moment_image(folder, at):
    """moment.jpg: the clip's frame at the bug (seconds into the clip)."""
    clip = Path(folder) / 'clip.mp4'
    return subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'fatal', '-y', '-ss', f'{max(0.0, at):.2f}', '-i', str(clip),
                           '-frames:v', '1', '-vf', "scale='min(1280,iw)':-2", '-q:v', '3', str(Path(folder) / 'moment.jpg')],
                          stdin=subprocess.DEVNULL).returncode == 0


def did_lines(did, bug_at, last=8):
    """The last actions as numbered lines, repeats merged: '3. SWITCH ×3 (9 s before the bug)'."""
    merged = []
    for at, what in did:
        if merged and merged[-1][1] == what:
            merged[-1][2] += 1
        else:
            merged.append([at, what, 1])
    out = []
    for i, (at, what, n) in enumerate(merged[-last:], 1):
        ago = bug_at - at
        when = 'at the bug' if abs(ago) < 0.5 else f'{ago:.0f} s before the bug' if ago > 0 else f'{-ago:.0f} s after'
        out.append(f'{i}. {what}{f" ×{n}" if n > 1 else ""} ({when})')
    return '\n'.join(out)


def report(ev, meta, touches, folder=None, t0=None, clip_seconds=None, desc=None):
    """Markdown report. desc: describe.describe()'s {'did', 'summary', 'situation'} (button names
    read off the screen); without it the taps are named by where they were."""
    folder = Path(folder) if folder else None
    if desc is None and t0 is not None:
        from . import describe
        named = [(a[0] - t0, describe.name(a, [])[0]) for a in describe.actions(touches, t0)]
        desc = {'did': named, 'summary': describe.summary([(w, 0) for _, w in named]), 'situation': ''}
    bug_at = ev.ts - t0 if t0 is not None else 0
    if desc and desc['did']:
        steps = f"**{desc['summary']}**\n\n" + did_lines(desc['did'], bug_at)
    else:
        steps = 'No taps recorded: watch clip.mp4.'
    situation = f"| On screen | {desc['situation']} |\n" if desc and desc.get('situation') else ''
    moment = '\n![the moment of the bug](moment.jpg)\n' if folder and (folder / 'moment.jpg').exists() else ''
    if ev.kind == 'manual':
        actual = ev.note or '_Describe what went wrong (see clip.mp4)._'
        expected = '_What should have happened?_'
    elif ev.kind in SEEN:
        actual = (ev.lines[0] if ev.lines else KIND_LABEL[ev.kind]) + (f'. Tester: {ev.note}' if ev.note else '')
        expected = {'lag': 'The game stays smooth (45-60 fps).',
                    'text': 'Every label shows real text, not a key or a placeholder.',
                    'glitch': 'Every model and surface has its texture.'}.get(ev.kind, 'The game reacts to every tap.')
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
{situation}
## What happened
{actual}

**Watch `clip.mp4`**: {length} leading up to the bug. White dots show where the tester's finger touched; the FPS meter is top-left.
{moment}
## Expected
{expected}

## What the tester did ({length} before)
{steps}

## Attachments
- {', '.join(f'`{n}`' for n in ('clip.mp4', 'moment.jpg') if folder and (folder / n).exists()) or 'no video'}{chr(10) + '- `full.mp4`: the 30 s before, in case the moment came earlier' if folder and (folder / 'full.mp4').exists() else ''}
- `logcat.txt` (device log), `touches.jsonl` (raw taps)
"""


def write(root, ev, meta, logs, touches, make_clip, t0=None, clip_seconds=None):
    """Writes the bug folder; `make_clip(path)` cuts the video. Returns the folder."""
    folder = Path(root) / f"{time.strftime('%Y%m%d-%H%M%S', time.localtime(ev.ts))}_{ev.kind}"
    folder.mkdir(parents=True, exist_ok=True)
    has_clip = make_clip(folder / 'clip.mp4')
    desc = None
    if has_clip and t0 is not None:
        moment_image(folder, ev.ts - t0)
        from . import describe
        try:
            desc = describe.describe(folder / 'clip.mp4', touches, t0, ev.ts - t0)
        except Exception:
            desc = None            # the report still names taps by position
    if desc:
        (folder / 'describe.json').write_text(json.dumps(desc))
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
    saved = folder / 'describe.json'
    desc = json.loads(saved.read_text()) if saved.exists() else None
    (folder / 'report.md').write_text(report(ev, meta, touches, folder, t0, clip_seconds, desc))


def load(folder):
    """(Event, meta, touches) back from a bug folder on disk."""
    from .logcat import Event
    folder = Path(folder)
    m = json.loads((folder / 'meta.json').read_text())
    ts = time.mktime(time.strptime(m['time'], '%Y-%m-%d %H:%M:%S'))
    ev = Event(m['kind'], ts, lines=m.get('matched_lines') or [], note=m.get('note') or '')
    touches_file = folder / 'touches.jsonl'
    touches = [(t['host_ts'], t) for t in map(json.loads, touches_file.read_text().splitlines())] if touches_file.exists() else []
    meta = {k: m[k] for k in ('model', 'android', 'package', 'game_version', 'serial') if k in m}
    return ev, meta, touches, m


def rebuild(folder):
    """Re-reads the clip (button names, scoreboard, moment.jpg) and rewrites the report."""
    folder = Path(folder)
    ev, meta, touches, m = load(folder)
    t0, length = m.get('clip_start'), m.get('clip_seconds')
    has_clip = (folder / 'clip.mp4').exists()
    if has_clip and t0 is not None:
        moment_image(folder, ev.ts - t0)
        from . import describe
        desc = describe.describe(folder / 'clip.mp4', touches, t0, ev.ts - t0)
        if desc:
            (folder / 'describe.json').write_text(json.dumps(desc))
    update(folder, ev, meta, touches, has_clip, t0, length)
