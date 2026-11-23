"""Bug reports for Discord, the way the studio already reports bugs. Lens never posts anything itself:
the tester copies the message (Discord Markdown, under 2,000 characters) and the clip, and pastes them.
Discord takes 20 MB per message here (the tester's limit): a clip that fits is used as it is, a bigger one is
re-encoded to 1280 px wide.
"""
import json
import subprocess
from pathlib import Path

from . import bugs

LIMIT = 19.5 * 1024 * 1024      # bytes per message (Discord's 20 MB), with room for the text
MAX_CHARS = 2000


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

