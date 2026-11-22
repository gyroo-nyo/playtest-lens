"""Bug reports to a Discord channel, the way the studio already reports bugs.

Two ways, both started by the tester:
- Copy for Discord: the message as Discord Markdown (under 2,000 characters) to paste yourself.
- Send to Discord: posts the message with a small copy of the clip and the picture through a channel
  webhook the tester pastes once (Server Settings → Integrations → Webhooks). Nothing is sent otherwise.
Discord takes 20 MB per message here (the tester's limit): a clip that fits goes as it is, a bigger one is
re-encoded to 1280 px wide.
"""
import json
import re
import subprocess
import time
import urllib.request
import uuid
from pathlib import Path

from . import bugs

WEBHOOK = re.compile(r'https://(?:(?:ptb|canary)\.)?discord(?:app)?\.com/api/webhooks/\d+/[\w-]+')
LIMIT = 19.5 * 1024 * 1024      # bytes per message (Discord's 20 MB), with room for the text
MAX_CHARS = 2000


def valid(url):
    return bool(WEBHOOK.fullmatch((url or '').strip()))


def message(folder, details=False):
    """The bug as one Discord message: the tester's explanation (the way GFL bugs are reported),
    plus with `details` the scoreboard, the buttons pressed and the device. At most 2,000 characters."""
    folder = Path(folder)
    ev, meta, touches, m = bugs.load(folder)
    read = lambda n: json.loads((folder / n).read_text(encoding='utf-8')) if (folder / n).exists() else {}
    desc, ai = read('describe.json'), read('ai.json')
    kind = bugs.KIND_LABEL.get(ev.kind, 'Bug')
    title = ai.get('title') or bugs.title(ev)
    if not details:
        said = ev.note if ev.kind == 'manual' else (ev.lines[0] if ev.lines else title)
        if ev.kind != 'manual' and ev.note:
            said += f'\n{ev.note}'
        text = said or title
        return text if len(text) <= MAX_CHARS else text[:MAX_CHARS - 1] + '…'
    lines = [f'**[{kind}] {title}**']
    if desc.get('situation'):
        lines.append(f"> On screen: {desc['situation']}")
    if desc.get('summary'):
        lines.append(f"> Pressed (last 15 s): {desc['summary']}")
    what = ai.get('actual') or (ev.note if ev.kind == 'manual' else (ev.lines[0] if ev.lines else '')) or ''
    if what and what != title:
        lines.append(f'**What happened:** {what}')
    if ai.get('expected'):
        lines.append(f"**Expected:** {ai['expected']}")
    if ai.get('steps'):
        lines.append('**Steps:**\n' + '\n'.join(f'{i}. {s}' for i, s in enumerate(ai['steps'], 1)))
    if ev.kind in ('crash', 'anr') and ev.lines:
        lines.append('```\n' + '\n'.join(ev.lines[:6])[:600] + '\n```')
    lines.append(f"-# {meta.get('model')} · Android {meta.get('android')} · {meta.get('package')} "
                 f"{meta.get('game_version')} · {m.get('time')} · Playtest Lens")
    text = '\n'.join(lines)
    return text if len(text) <= MAX_CHARS else text[:MAX_CHARS - 1] + '…'


def small_clip(folder, name='clip.mp4'):
    """The video (clip.mp4, or full.mp4: the 30 s before) as it is when it fits under Discord's limit, else a
    1280 px copy (discord.mp4 / discord-full.mp4) with the bitrate capped by its length so it stays well under."""
    folder = Path(folder)
    src = folder / name
    out = folder / ('discord.mp4' if name == 'clip.mp4' else f'discord-{Path(name).stem}.mp4')
    if not src.exists():
        return None
    if src.stat().st_size <= LIMIT - 1024 * 1024:
        return src
    if out.exists() and out.stat().st_mtime >= src.stat().st_mtime:
        return out
    probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(src)],
                           stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding='utf-8').stdout
    try:
        seconds = float(probe)
    except ValueError:
        seconds = 15.0
    rate = int(7000 * 15 / max(15.0, seconds))      # 7000k for 15 s (about 13 MB); longer videos get less per second
    ok = subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'fatal', '-y', '-i', str(src), '-vf', "scale='min(1280,iw)':-2",
                         '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23', '-maxrate', f'{rate}k', '-bufsize', f'{2 * rate}k',
                         '-pix_fmt', 'yuv420p', '-an', '-movflags', '+faststart', str(out)], stdin=subprocess.DEVNULL).returncode == 0
    return out if ok else None


def multipart(fields, files):
    """(body, content type) for multipart/form-data. files: [(field, filename, bytes, mime)]."""
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n'
                     f'Content-Type: application/json\r\n\r\n'.encode() + value.encode() + b'\r\n')
    for field, filename, data, mime in files:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
                     f'Content-Type: {mime}\r\n\r\n'.encode() + data + b'\r\n')
    return b''.join(parts) + f'--{boundary}--\r\n'.encode(), f'multipart/form-data; boundary={boundary}'


def send(webhook, folder, post=None, details=False):
    """Posts the bug to the channel. Returns {'sent': time, 'files': [...]} or raises ValueError with
    a message the tester can act on. `post(url, body, content_type)` is for tests."""
    if not valid(webhook):
        raise ValueError('That isn\'t a Discord webhook link. In Discord: Server Settings → Integrations → Webhooks → Copy Webhook URL.')
    folder = Path(folder)
    files, size = [], 0
    clip = small_clip(folder)
    circled = folder / 'circled.jpg'
    # short reports: the clip is enough, unless the tester circled the problem
    picture = circled if circled.exists() else folder / 'moment.jpg' if details or not clip else None
    for path, mime in ((clip, 'video/mp4'), (picture, 'image/jpeg')):
        if path and path.exists() and size + path.stat().st_size <= LIMIT:
            data = path.read_bytes()
            files.append((f'files[{len(files)}]', 'clip.mp4' if mime == 'video/mp4' else path.name, data, mime))
            size += len(data)
    payload = {'content': message(folder, details), 'allowed_mentions': {'parse': []},
               'attachments': [{'id': i, 'filename': f[1]} for i, f in enumerate(files)]}
    body, kind = multipart({'payload_json': json.dumps(payload)}, files)
    post = post or _post
    status, reply = post(webhook.strip() + '?wait=true', body, kind)
    if status == 413:
        raise ValueError('Discord said the clip is too big for this server. Use Copy for Discord and attach a shorter clip.')
    if status in (401, 404):
        raise ValueError('Discord doesn\'t know that webhook anymore (deleted?). Paste a new webhook link.')
    if status >= 300:
        raise ValueError(f'Discord refused the message ({status}). Try Copy for Discord instead.')
    sent = {'sent': time.strftime('%Y-%m-%d %H:%M:%S'), 'files': [f[1] for f in files]}
    (folder / 'discord.json').write_text(json.dumps(sent), encoding='utf-8')
    return sent


def _post(url, body, kind):
    req = urllib.request.Request(url, body, {'Content-Type': kind, 'User-Agent': 'PlaytestLens (local bug reporter)'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except OSError as e:
        raise ValueError(f'Couldn\'t reach Discord: {e}. Check the internet connection.')
