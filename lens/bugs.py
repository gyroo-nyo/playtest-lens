"""One folder per bug: clip, logs, touches, metadata and a report a tester can paste."""
import json
import re
import subprocess
import time
from pathlib import Path

from .logcat import headline

KIND_LABEL = {'crash': 'Crash', 'anr': 'App not responding', 'manual': 'Bug',
              'freeze': 'Freeze', 'lag': 'Frame drops', 'text': 'Text bug', 'glitch': 'Visual glitch',
              'closed': 'Game closed'}
SEEN = ('freeze', 'lag', 'text', 'glitch', 'closed')   # Lens's own one-line description is the title


def title(ev):
    if ev.kind == 'manual':
        return ev.note or 'Marked by tester'
    if ev.kind in SEEN:
        return ev.note or (ev.lines[0] if ev.lines else KIND_LABEL[ev.kind])
    return headline(ev.lines) or KIND_LABEL[ev.kind]


GROUPED = ('crash', 'anr', 'text', 'closed')   # the same error text = the same bug; lag, freeze, glitch and marks differ each time


def signature(kind, title):
    """What makes two bugs the same: the error with its numbers (pids, addresses, line numbers) left out. None: not grouped."""
    return f"{kind}:{re.sub(r'0x[0-9a-f]+|\d+', '#', title.lower())}" if kind in GROUPED else None


def seen_before(folder, kind, title_text):
    """[(bug id, game version)] of the saved bugs before this one with the same error, oldest first (false alarms don't count)."""
    folder = Path(folder)
    sig = signature(kind, title_text)
    if not sig or folder.parent.name == FALSE:
        return []
    out = []
    for f in sorted(folder.parent.iterdir()):
        if f.name >= folder.name or not f.is_dir() or f.name.startswith(('_', '.')):
            continue
        try:
            m = json.loads((f / 'meta.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if signature(m.get('kind'), m.get('title', '')) == sig:
            out.append((f.name, m.get('game_version', '?')))
    return out


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
    from .health import line as health_line
    phone = f"| Phone | {health_line(meta['health'])} |\n" if meta.get('health') else ''
    before = seen_before(folder, ev.kind, title(ev)) if folder else []
    if before:
        first = time.strptime(before[0][0].split('_')[0], '%Y%m%d-%H%M%S')
        builds = ', '.join(dict.fromkeys(v for _, v in before))
        phone += f"| Seen before | {len(before)} time{'s' * (len(before) > 1)}, first {time.strftime('%d %b %H:%M', first)} · builds {builds} |\n"
    pic = picture(folder) if folder else None
    moment = f'\n![the moment of the bug]({pic.name})\n' if pic else ''
    if ev.kind == 'manual':
        actual = ev.note or '_Describe what went wrong (see clip.mp4)._'
        expected = '_What should have happened?_'
    elif ev.kind in SEEN:
        actual = (ev.lines[0] if ev.lines else KIND_LABEL[ev.kind]) + (f'. Tester: {ev.note}' if ev.note else '')
        expected = {'lag': 'The game stays smooth (45-60 fps).',
                    'text': 'Every label shows real text, not a key or a placeholder.',
                    'glitch': 'Every model and surface has its texture.',
                    'closed': 'The game keeps running.'}.get(ev.kind, 'The game reacts to every tap.')
    else:
        actual = ev.note or (f'The game {"crashed" if ev.kind == "crash" else "stopped responding"}: `{title(ev)}`')
        expected = 'The game keeps running normally.'
    length = f'{clip_seconds:.0f} s' if clip_seconds else 'the moments'
    heading = title(ev)
    repro = ''
    if desc and desc.get('situation') and desc.get('did'):     # without an AI draft: start from the same spot, press the same
        repro = (f"## Steps to reproduce\n1. Get to the same spot: {desc['situation']}\n"
                 f"2. Press what the tester pressed (below), then watch for the bug.\n\n")
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
{phone}{situation}
## What happened
{actual}

**Watch `clip.mp4`**: {length} leading up to the bug. White dots show where the tester's finger touched; the FPS meter is top-left.
{moment}
## Expected
{expected}

{repro}**Pressed in the {length} before:** {steps}
"""


def bug_id(ev):
    return f"{time.strftime('%Y%m%d-%H%M%S', time.localtime(ev.ts))}_{ev.kind}"


def write(root, ev, meta, logs, touches, make_clip, t0=None, clip_seconds=None):
    """Writes the bug folder; `make_clip(path)` cuts the video. Returns the folder."""
    folder = Path(root) / bug_id(ev)
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
    if not meta.get('health') and (folder / 'meta.json').exists():     # a later note or rebuild keeps the reading from the bug
        meta = {**meta, 'health': json.loads((folder / 'meta.json').read_text(encoding='utf-8')).get('health')}
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
    meta = {k: m[k] for k in ('model', 'android', 'package', 'game_version', 'serial', 'pids', 'health') if k in m}
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
        return {'id': folder.name, 'kind': m.get('kind', 'manual'), 'sig': signature(m.get('kind'), m.get('title', '')), 'time': m.get('time', ''), 'title': m.get('title', ''),
                'note': m.get('note') or '', 'clip': (folder / 'clip.mp4').exists(), 'full': (folder / 'full.mp4').exists(),
                'clip_seconds': m.get('clip_seconds'), 'sent': (folder / 'discord.json').exists(), 'situation': desc.get('situation', ''), 'summary': desc.get('summary', '')}

    def rows(where):
        found = [row(f) for f in where.iterdir() if f.is_dir() and not f.name.startswith(('_', '.'))] if where.exists() else []
        found = sorted((r for r in found if r), key=lambda r: r['id'], reverse=True)
        counts = {}
        for r in found:
            counts[r['sig']] = counts.get(r['sig'], 0) + 1
        for r in found:
            sig = r.pop('sig')
            r['seen'] = counts[sig] if sig else 1      # how many saved bugs share this error, this one included
        return found
    return {'bugs': rows(root), 'false_alarms': rows(root / FALSE)}


def older(root, when, now=None):
    """Bug and false-alarm folders saved before `when`: 'today' (before today), 'week' (over 7 days old) or 'all'.
    Never one saved in the last minute: it may still be being written."""
    import time as _time
    now = now or _time.time()
    cutoff = {'today': _time.mktime(_time.localtime(now)[:3] + (0, 0, 0, 0, 0, -1)), 'week': now - 7 * 86400, 'all': now - 60}[when]
    root = Path(root)
    out = []
    for where in (root, root / FALSE):
        for f in (where.iterdir() if where.exists() else []):
            if not f.is_dir() or f.name.startswith(('_', '.')) or not (f / 'meta.json').exists():
                continue
            try:
                saved = _time.mktime(_time.strptime(f.name[:15], '%Y%m%d-%H%M%S'))
            except ValueError:
                continue
            if saved < min(cutoff, now - 60):
                out.append(f)
    return out


def trash(folders):
    """Moves folders to the Trash (macOS) or Recycle Bin (Windows), so a wrong delete can be undone.
    Returns the ones that are gone."""
    import shutil, subprocess, sys
    paths = [str(Path(f).resolve()) for f in folders]
    if not paths:
        return []
    if sys.platform == 'darwin':
        js = ("ObjC.import('Foundation'); function run(a) { const fm = $.NSFileManager.defaultManager;"
              " a.forEach(p => fm.trashItemAtURLResultingItemURLError($.NSURL.fileURLWithPath(p), null, null)); }")
        subprocess.run(['osascript', '-l', 'JavaScript', '-e', js, *paths], stdin=subprocess.DEVNULL, capture_output=True)
    elif sys.platform == 'win32':
        ps = ("Add-Type -AssemblyName Microsoft.VisualBasic; foreach ($p in $args) { "
              "[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory($p, 'OnlyErrorDialogs', 'SendToRecycleBin') }")
        subprocess.run(['powershell', '-NoProfile', '-Command', ps, *paths], stdin=subprocess.DEVNULL, capture_output=True)
    else:
        for p in paths:
            shutil.rmtree(p, ignore_errors=True)
    return [p for p in paths if not Path(p).exists()]


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


def picture(folder):
    """The bug's picture: the one the tester circled the problem on, else the plain moment.jpg. None if neither."""
    return next((p for p in (Path(folder) / 'circled.jpg', Path(folder) / 'moment.jpg') if p.exists()), None)


def set_circled(root, bug_id, jpeg, circles=()):
    """Saves the moment picture with the tester's circles (circled.jpg; moment.jpg stays as it was), or removes it (None)."""
    folder = find(root, bug_id)
    if not folder:
        return None
    if jpeg:
        (folder / 'circled.jpg').write_bytes(jpeg)
        (folder / 'circles.json').write_text(json.dumps(list(circles)), encoding='utf-8')
    else:
        (folder / 'circled.jpg').unlink(missing_ok=True)
        (folder / 'circles.json').unlink(missing_ok=True)
    ev, meta, touches, m = load(folder)
    update(folder, ev, meta, touches, (folder / 'clip.mp4').exists(), m.get('clip_start'), m.get('clip_seconds'))
    return folder


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
