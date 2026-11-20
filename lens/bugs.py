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


def report(ev, meta, touches, folder=None, t0=None, clip_seconds=None, desc=None, ai=None):
    """Markdown report. desc: describe.describe()'s {'did', 'summary', 'situation'} (button names
    read off the screen); without it the taps are named by where they were."""
    folder = Path(folder) if folder else None
    if desc is None and t0 is not None:
        from . import describe
        named = [(a[0] - t0, describe.name(a, [])[0]) for a in describe.actions(touches, t0)]
        desc = {'did': named, 'summary': describe.summary([(w, 0) for _, w in named]), 'situation': ''}
    bug_at = ev.ts - t0 if t0 is not None else 0
    if desc and desc['did']:
        steps = desc['summary']
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
    heading = title(ev)
    repro = ''
    if ai:      # a local model's draft (writer.py): its words for title, actual, expected and steps
        heading, actual, expected = ai['title'], ai.get('actual') or actual, ai.get('expected') or expected
        if ai.get('steps'):
            repro = '## Steps to reproduce\n' + '\n'.join(f'{i}. {st}' for i, st in enumerate(ai['steps'], 1)) + '\n\n'
        if ai.get('severity'):
            actual += f"\n\n**Severity (suggested):** {ai['severity']}"
    return f"""# [{KIND_LABEL[ev.kind]}] {heading}

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

{repro}**Pressed in the {length} before:** {steps}
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
        (folder / 'describe.json').write_text(json.dumps(desc), encoding='utf-8')
    (folder / 'logcat.txt').write_text('\n'.join(line for _, line in logs) + '\n', encoding='utf-8')
    (folder / 'touches.jsonl').write_text(''.join(json.dumps({'host_ts': round(ts, 3), **t}) + '\n' for ts, t in touches), encoding='utf-8')
    update(folder, ev, meta, touches, has_clip, t0, clip_seconds)
    return folder


def update(folder, ev, meta, touches, has_clip=True, t0=None, clip_seconds=None):
    """(Re)writes meta and report, e.g. when the tester's note arrives after the clip."""
    folder = Path(folder)
    (folder / 'meta.json').write_text(json.dumps({**meta, 'kind': ev.kind, 'time': stamp(ev.ts), 'title': title(ev),
                                                  'note': ev.note, 'matched_lines': ev.lines, 'clip': has_clip,
                                                  'clip_start': t0, 'clip_seconds': clip_seconds}, indent=2), encoding='utf-8')
    saved = folder / 'describe.json'
    desc = json.loads(saved.read_text(encoding='utf-8')) if saved.exists() else None
    drafted = folder / 'ai.json'
    ai = json.loads(drafted.read_text(encoding='utf-8')) if drafted.exists() else None
    if not (folder / 'report.edited.md').exists():       # never overwrite what the tester wrote
        (folder / 'report.md').write_text(report(ev, meta, touches, folder, t0, clip_seconds, desc, ai), encoding='utf-8')


def load(folder):
    """(Event, meta, touches) back from a bug folder on disk."""
    from .logcat import Event
    folder = Path(folder)
    m = json.loads((folder / 'meta.json').read_text(encoding='utf-8'))
    ts = time.mktime(time.strptime(m['time'], '%Y-%m-%d %H:%M:%S'))
    ev = Event(m['kind'], ts, lines=m.get('matched_lines') or [], note=m.get('note') or '')
    touches_file = folder / 'touches.jsonl'
    touches = [(t['host_ts'], t) for t in map(json.loads, touches_file.read_text(encoding='utf-8').splitlines())] if touches_file.exists() else []
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
            (folder / 'describe.json').write_text(json.dumps(desc), encoding='utf-8')
    update(folder, ev, meta, touches, has_clip, t0, length)


FALSE = '_false_alarms'


def listing(root):
    """{'bugs': [...], 'false_alarms': [...]}, newest first: what the dashboard's feed shows."""
    root = Path(root)

    def row(folder):
        try:
            m = json.loads((folder / 'meta.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return None
        d = folder / 'describe.json'
        desc = json.loads(d.read_text(encoding='utf-8')) if d.exists() else {}
        return {'id': folder.name, 'kind': m.get('kind', 'manual'), 'time': m.get('time', ''), 'title': m.get('title', ''),
                'note': m.get('note') or '', 'clip': (folder / 'clip.mp4').exists(), 'full': (folder / 'full.mp4').exists(),
                'clip_seconds': m.get('clip_seconds'), 'sent': (folder / 'discord.json').exists(), 'situation': desc.get('situation', ''), 'summary': desc.get('summary', '')}

    def rows(where):
        found = [row(f) for f in where.iterdir() if f.is_dir() and not f.name.startswith(('_', '.'))] if where.exists() else []
        return sorted((r for r in found if r), key=lambda r: r['id'], reverse=True)
    return {'bugs': rows(root), 'false_alarms': rows(root / FALSE)}


def find(root, bug_id):
    """The folder for a bug id, in the feed or among false alarms; None for anything else (no ../)."""
    root = Path(root).resolve()
    if not bug_id or '/' in bug_id or bug_id.startswith(('.', '_')):
        return None
    for where in (root, root / FALSE):
        folder = (where / bug_id).resolve()
        if folder.parent == where.resolve() and (folder / 'meta.json').exists():
            return folder
    return None


def dismiss(root, bug_id):
    """A wrong catch: moved (not deleted) to _false_alarms, where it can tune the detectors."""
    folder = find(root, bug_id)
    if not folder or folder.parent.name == FALSE:
        return False
    dest = Path(root) / FALSE / bug_id
    dest.parent.mkdir(parents=True, exist_ok=True)
    folder.rename(dest)
    return True


def restore(root, bug_id):
    folder = find(root, bug_id)
    if not folder or folder.parent.name != FALSE:
        return False
    folder.rename(Path(root) / bug_id)
    return True


def save_report(root, bug_id, text):
    """The tester's edited report.md. Rebuilding keeps it in report.edited.md, never overwritten."""
    folder = find(root, bug_id)
    if not folder:
        return False
    (folder / 'report.md').write_text(text, encoding='utf-8')
    (folder / 'report.edited.md').write_text(text, encoding='utf-8')
    return True


def set_note(root, bug_id, text):
    """The tester's comment on a saved bug: becomes its title and goes into the report."""
    folder = find(root, bug_id)
    if not folder:
        return None
    ev, meta, touches, m = load(folder)
    ev.note = text.strip()[:300]
    update(folder, ev, meta, touches, (folder / 'clip.mp4').exists(), m.get('clip_start'), m.get('clip_seconds'))
    return folder


def write_with_ai(root, bug_id):
    """Asks the local model for a draft and rewrites report.md with it. Returns the draft; {'error': 'note'}
    when a manual mark's note is too short to rewrite; None when no local model answers."""
    from . import writer
    folder = find(root, bug_id)
    if not folder:
        return None
    ev, meta, touches, m = load(folder)
    if ev.kind == 'manual' and len(ev.note.split()) < 3:
        return {'error': 'note'}      # "error" isn't enough to go on: the model would make the bug up
    d = folder / 'describe.json'
    desc = json.loads(d.read_text(encoding='utf-8')) if d.exists() else None
    ai = writer.draft(writer.facts(KIND_LABEL[ev.kind], title(ev), ev.note, meta, desc, ev.lines))
    if not ai:
        return None
    (folder / 'ai.json').write_text(json.dumps(ai, indent=2), encoding='utf-8')
    (folder / 'report.edited.md').unlink(missing_ok=True)   # asked for a new draft: replace the old text
    update(folder, ev, meta, touches, (folder / 'clip.mp4').exists(), m.get('clip_start'), m.get('clip_seconds'))
    return ai
