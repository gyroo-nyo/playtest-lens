"""The dashboard: a local web page for the bug feed, clips, reports and (while `lens watch` runs) the live phone.

Standard library only. Binds to 127.0.0.1: clips can show private chats and games under NDA, so
nothing else on the network may reach it. Serves files only from inside the bugs folder, supports
HTTP Range so Safari can play and seek the clips, answers only requests addressed to 127.0.0.1 or
localhost (no DNS rebinding), and only accepts actions sent with the page's own header.
"""
import json
import mimetypes
import re
import subprocess
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import bugs, checks, discord

PAGE = Path(__file__).parent / 'web' / 'index.html'
FONTS = Path(__file__).parent / 'web' / 'fonts'
FILES = {'clip.mp4', 'full.mp4', 'moment.jpg'}
PUBLIC = ('github_repo', 'package', 'discord_details')   # settings the page may see; the Discord webhook is a secret
PORT = 8737
CHECKS = threading.Lock()      # the page can send two clicks at once: one read-modify-write of .checks.json at a time


class Live:
    """What `lens watch` shares with the page. Without it the page shows the saved bugs only."""

    def __init__(self, package, version, model, mark):
        self.package, self.version, self.model, self.mark = package, version, model, mark
        self.started = time.time()
        self.fps = None
        self.fps_ts = 0.0
        self.connected = True
        self.video = True           # frames are arriving (False: the stream died or the screen sat still)
        self.health = None          # the latest phone health reading (health.py)
        self.alarm = False          # a real outage: the game is drawing (or the phone dropped off) and no video arrives
        self.caught = []           # (ts, kind, title) of this session's catches, newest last
        self.note = None           # add_note(text): the comment for the latest mark
        self.marks = None          # marks.Marks: which mark is waiting for a comment

    def state(self):
        now = time.time()
        return {'package': self.package, 'version': self.version, 'model': self.model, 'connected': self.connected, 'video': self.video, 'alarm': self.alarm, 'health': self.health,
                'fps': self.fps if now - self.fps_ts < 3 else None, 'recording_for': round(now - self.started),
                'caught': self.caught[-20:], 'waiting_note': self.waiting_note()}

    def waiting_note(self):
        return self.marks.waiting() if self.marks else None


def settings_path(root):
    return Path(root) / '.lens.json'


def settings(root):
    try:
        return json.loads(settings_path(root).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def reveal(path):
    """Show a file selected in Finder (macOS) or File Explorer (Windows)."""
    if sys.platform == 'darwin':
        subprocess.run(['open', '-R', str(path)], stdin=subprocess.DEVNULL)
    elif sys.platform == 'win32':
        subprocess.run(f'explorer /select,"{path}"', stdin=subprocess.DEVNULL)   # explorer wants the path glued to /select,


def copy_file(path):
    """Put the file itself on the clipboard, so ⌘V / Ctrl+V in Discord attaches it. False if that didn't work."""
    if sys.platform == 'darwin':
        # AppleScript's `set the clipboard to POSIX file` left the clipboard empty about 1 time in 5 while saying it
        # worked, so write the file URL through NSPasteboard and read it back to be sure.
        cmd = ['osascript', '-l', 'JavaScript', '-e', MAC_COPY, str(Path(path).resolve())]
        for _ in range(3):
            r = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding='utf-8')
            if r.stdout.strip() == 'ok':
                return True
        return False
    elif sys.platform == 'win32':
        cmd = ['powershell', '-NoProfile', '-Command', 'Set-Clipboard -LiteralPath $args[0]', str(Path(path).resolve())]
    else:
        return False
    return subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True).returncode == 0


MAC_COPY = """ObjC.import('AppKit');
function run(a) {
  const pb = $.NSPasteboard.generalPasteboard;
  pb.clearContents;
  const url = $.NSURL.fileURLWithPath(a[0]);
  const ok = pb.writeObjects($([url]));
  const got = pb.stringForType('public.file-url');
  return (ok && got.js === url.absoluteString.js) ? 'ok' : 'fail';
}"""


def public(root):
    s = settings(root)
    return {**{k: s[k] for k in PUBLIC if k in s}, 'discord': bool(s.get('discord_webhook'))}


def save_settings(root, **changes):
    s = {**settings(root), **changes}
    settings_path(root).parent.mkdir(parents=True, exist_ok=True)
    settings_path(root).write_text(json.dumps(s, indent=2), encoding='utf-8')
    return s


def issue_url(repo, report_md):
    """A prefilled 'new issue' page on GitHub. Nothing is posted: the tester reviews and submits it."""
    if not re.fullmatch(r'[\w.-]+/[\w.-]+', repo or ''):
        return None
    lines = report_md.splitlines()
    title = re.sub(r'^#\s*', '', lines[0]) if lines else 'Bug'
    body = '\n'.join(l for l in lines[1:] if not l.startswith('![')).strip()
    body += '\n\n_Attach clip.mp4 and moment.jpg from the bug folder._'
    q = urllib.parse.urlencode({'title': title, 'body': body[:6000]})
    return f'https://github.com/{repo}/issues/new?{q}'


def detail(root, bug_id):
    folder = bugs.find(root, bug_id)
    if not folder:
        return None
    m = json.loads((folder / 'meta.json').read_text(encoding='utf-8'))
    read = lambda name: (folder / name).read_text(encoding='utf-8') if (folder / name).exists() else None
    t0 = m.get('clip_start')
    ev_ts = time.mktime(time.strptime(m['time'], '%Y-%m-%d %H:%M:%S')) if m.get('time') else None
    taps = []
    if t0 is not None and (folder / 'touches.jsonl').exists():
        for line in (folder / 'touches.jsonl').read_text(encoding='utf-8').splitlines():
            t = json.loads(line)
            if t.get('type') == 'down' and t['host_ts'] >= t0:
                taps.append(round(t['host_ts'] - t0, 2))
    full_log = (read('logcat.txt') or '').splitlines()
    log = full_log[-400:]
    # The game's own lines: anything its process wrote (any game, any engine), plus lines that name it, like
    # `adb logcat | grep -Ei "<package>|libgdx|lerr|laux|androidruntime|system.err|system.out"`
    game_pids = {str(x) for x in m.get('pids') or []}
    game = re.compile('|'.join([re.escape(m.get('package') or 'superfusion.gfl'), 'libgdx', 'lerr', 'laux', 'androidruntime',
                                r'system\.err', r'system\.out']), re.I)
    lens_own = re.compile(r' adbd\s*:|BufferQueueProducer')     # Lens's own adb commands and the FPS readings it takes
    pid_of = lambda l: (l.split()[1:2] or [''])[0]
    game_log = [l for l in full_log if (pid_of(l) in game_pids or game.search(l)) and not lens_own.search(l)][-1500:]
    matched = set(m.get('matched_lines') or [])
    return {
        'id': bug_id, 'false_alarm': folder.parent.name == bugs.FALSE, 'meta': m,
        'report': read('report.md') or '', 'edited': (folder / 'report.edited.md').exists(),
        'describe': json.loads(read('describe.json') or 'null'), 'ai': json.loads(read('ai.json') or 'null'),
        'files': sorted(n for n in FILES if (folder / n).exists()),
        'discord': json.loads(read('discord.json') or 'null'),
        'bug_at': round(ev_ts - t0, 2) if ev_ts and t0 is not None else None, 'taps': taps,
        'log': [{'text': l, 'hit': any(x and x in l for x in matched)} for l in log],
        'game_log': [{'text': l, 'hit': any(x and x in l for x in matched)} for l in game_log],
    }


class Handler(BaseHTTPRequestHandler):
    root = Path('bugs')
    live = None

    def log_message(self, *a):     # keep the terminal for Lens's own messages
        pass

    def send(self, code, body=b'', kind='application/json', extra=None):
        if isinstance(body, (dict, list)) or body is None:
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def file(self, path, kind):
        size = path.stat().st_size
        rng = re.fullmatch(r'bytes=(\d*)-(\d*)', self.headers.get('Range', ''))
        start, end = 0, size - 1
        if rng and (rng.group(1) or rng.group(2)):
            if rng.group(1):
                start = int(rng.group(1))
                end = min(int(rng.group(2)), size - 1) if rng.group(2) else size - 1
            else:                                  # "bytes=-500": the last 500 bytes
                start = max(0, size - int(rng.group(2)))
            if start > end or start >= size:
                return self.send(416, b'', 'text/plain', {'Content-Range': f'bytes */{size}'})
        with open(path, 'rb') as f:
            f.seek(start)
            data = f.read(end - start + 1)
        headers = {'Accept-Ranges': 'bytes'}
        if rng and (rng.group(1) or rng.group(2)):
            headers['Content-Range'] = f'bytes {start}-{end}/{size}'
        self.send(206 if 'Content-Range' in headers else 200, data, kind, headers)

    def local(self):
        """Only requests addressed to this Mac. A page on another domain that re-points its name to
        127.0.0.1 (DNS rebinding) would otherwise count as this page and could read the clips."""
        port = self.server.server_address[1]
        if self.headers.get('Host') in (f'127.0.0.1:{port}', f'localhost:{port}'):
            return True
        self.send(403, {'error': 'forbidden'})
        return False

    def checks_state(self, data):
        build = self.live.version if self.live else data.get('last_build')
        return {**data, 'build': build, 'recording': bool(self.live), 'report': checks.report(data, build) if build else ''}

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if not self.local():
            return
        path = urllib.parse.urlparse(self.path).path
        if path == '/':
            return self.send(200, PAGE.read_bytes(), 'text/html; charset=utf-8')
        if path == '/api/state':
            return self.send(200, {'live': self.live.state() if self.live else None, **bugs.listing(self.root),
                                   'settings': public(self.root)})
        if path == '/api/checks':
            return self.send(200, self.checks_state(checks.load(self.root)))
        if m := re.fullmatch(r'/api/bug/([^/]+)', path):
            d = detail(self.root, urllib.parse.unquote(m.group(1)))
            return self.send(200 if d else 404, d)
        if m := re.fullmatch(r'/files/([^/]+)/([^/]+)', path):
            folder, name = bugs.find(self.root, urllib.parse.unquote(m.group(1))), m.group(2)
            if not folder or name not in FILES or not (folder / name).exists():
                return self.send(404, {'error': 'no such file'})
            return self.file(folder / name, mimetypes.guess_type(name)[0] or 'application/octet-stream')
        if m := re.fullmatch(r'/fonts/([a-z0-9-]+\.woff2)', path):
            font = FONTS / m.group(1)
            return self.file(font, 'font/woff2') if font.exists() else self.send(404, {'error': 'no such font'})
        self.send(404, {'error': 'not found'})

    def do_POST(self):
        if not self.local():
            return
        # Only the page itself sends this header; a cross-site form or fetch can't add it without CORS.
        if self.headers.get('X-Lens') != '1':
            return self.send(403, {'error': 'forbidden'})
        length = int(self.headers.get('Content-Length') or 0)
        try:
            body = json.loads(self.rfile.read(length) or b'{}')
        except ValueError:
            return self.send(400, {'error': 'bad json'})
        path = urllib.parse.urlparse(self.path).path
        if path == '/api/mark':
            if not self.live:
                return self.send(409, {'error': 'Not recording. Start `lens watch <package>` to mark bugs.'})
            self.live.mark(str(body.get('note', ''))[:300])
            return self.send(200, {'ok': True})
        if path == '/api/note':
            if not self.live or not self.live.note:
                return self.send(409, {'error': 'Not recording.'})
            text = str(body.get('text', '')).strip()[:300]
            if not text:
                return self.send(400, {'error': 'Write what went wrong first.'})
            self.live.note(text)
            return self.send(200, {'ok': True})
        if path == '/api/settings':
            changes = {}
            if 'github_repo' in body:
                repo = str(body['github_repo']).strip()
                if repo and not re.fullmatch(r'[\w.-]+/[\w.-]+', repo):
                    return self.send(400, {'error': 'Use owner/repo, e.g. superfusion/gfl-bugs'})
                changes['github_repo'] = repo
            if 'discord_webhook' in body:
                hook = str(body['discord_webhook']).strip()
                if hook and not discord.valid(hook):
                    return self.send(400, {'error': 'That isn\'t a Discord webhook link. In Discord: channel settings → Integrations → Webhooks → Copy Webhook URL.'})
                changes['discord_webhook'] = hook
            save_settings(self.root, **changes)
            return self.send(200, public(self.root))
        if path == '/api/checks':
            # {'add': text} | {'remove': id} | {'id': id, 'result': 'pass' | 'fail' | ''}. A fail is marked as a bug, with its clip.
            with CHECKS:
                data = checks.load(self.root)
                build = self.live.version if self.live else data.get('last_build')
                if 'add' in body:
                    if not checks.add(data, body['add']):
                        return self.send(400, {'error': 'Write the check first (and not one that\'s already on the list).'})
                else:
                    try:
                        cid = int(body.get('id') if 'remove' not in body else body['remove'])
                    except (TypeError, ValueError):
                        return self.send(400, {'error': 'Which check?'})
                    check = next((c for c in data['checks'] if c['id'] == cid), None)
                    if not check:
                        return self.send(404, {'error': 'That check is gone.'})
                    if 'remove' in body:
                        checks.remove(data, cid)
                    else:
                        res = body.get('result') or None
                        if res not in (None, 'pass', 'fail'):
                            return self.send(400, {'error': 'Pass or fail?'})
                        if not build:
                            return self.send(409, {'error': 'Start Lens with the phone plugged in, so it knows which build this is.'})
                        checks.result(data, build, cid, res)
                        if res == 'fail' and self.live and self.live.mark:
                            self.live.mark(f"Check failed: {check['text']}")
                checks.save(self.root, data)
                return self.send(200, self.checks_state(data))
        if path == '/api/cleanup':
            # Delete old bugs: {'when': 'today' | 'week' | 'all', 'dry': true} counts them first, then they go to the Trash.
            when = body.get('when')
            if when not in ('today', 'week', 'all'):
                return self.send(400, {'error': 'Pick which bugs to delete.'})
            found = bugs.older(self.root, when)
            if not body.get('dry'):
                found = [Path(p) for p in bugs.trash(found)]
            n_false = sum(1 for f in found if f.parent.name == bugs.FALSE)
            return self.send(200, {'bugs': len(found) - n_false, 'false_alarms': n_false,
                                   'mb': round(sum(x.stat().st_size for f in found if f.exists() for x in f.iterdir() if x.is_file()) / 1048576)})
        m = re.fullmatch(r'/api/bug/([^/]+)/(report|note|dismiss|restore|rebuild|ai|export|discord|discord-text|discord-clip)', path)
        if not m:
            return self.send(404, {'error': 'not found'})
        bug_id, action = urllib.parse.unquote(m.group(1)), m.group(2)
        if not bugs.find(self.root, bug_id):
            return self.send(404, {'error': 'no such bug'})
        if action == 'report':
            bugs.save_report(self.root, bug_id, str(body.get('text', '')))
        elif action == 'note':
            if not str(body.get('text', '')).strip():
                return self.send(400, {'error': 'Write what went wrong first.'})
            bugs.set_note(self.root, bug_id, str(body['text']))
        elif action == 'dismiss':
            bugs.dismiss(self.root, bug_id)
        elif action == 'restore':
            bugs.restore(self.root, bug_id)
        elif action == 'rebuild':
            bugs.rebuild(bugs.find(self.root, bug_id))
        elif action == 'ai':
            ai = bugs.write_with_ai(self.root, bug_id)
            if ai is None:
                return self.send(503, {'error': 'No local model answered. Start Ollama (ollama serve) and pull a model, e.g. ollama pull qwen2.5:7b.'})
            if ai.get('error') == 'note':
                return self.send(422, {'error': 'Write a note of a few words first: what went wrong? The model only rewrites what you saw.'})
        elif action == 'discord-text':
            details = bool(body.get('details', settings(self.root).get('discord_details')))
            if 'details' in body:
                save_settings(self.root, discord_details=details)      # the tickbox is remembered
            return self.send(200, {'text': discord.message(bugs.find(self.root, bug_id), details)})
        elif action == 'discord-clip':
            # For pasting by hand: the clip small enough for Discord, shown in Finder / Explorer to drag in.
            name = body.get('file', 'clip.mp4')
            if name not in ('clip.mp4', 'full.mp4'):
                return self.send(400, {'error': 'Pick the 15 s clip or the 30 s before.'})
            clip = discord.small_clip(bugs.find(self.root, bug_id), name)
            if not clip:
                return self.send(404, {'error': 'This bug has no clip.'})
            if body.get('copy'):
                if not copy_file(clip):
                    return self.send(500, {'error': 'Couldn\'t put the clip on the clipboard. Use Send to Discord, Copy text to find it in Finder.'})
            elif body.get('reveal', True):
                reveal(clip)
            return self.send(200, {'file': clip.name, 'mb': round(clip.stat().st_size / 1048576, 1)})
        elif action == 'discord':
            hook = settings(self.root).get('discord_webhook')
            if not hook:
                return self.send(409, {'error': 'Paste the channel\'s Discord webhook link first.'})
            try:
                discord.send(hook, bugs.find(self.root, bug_id), details=bool(settings(self.root).get('discord_details')))
            except ValueError as e:
                return self.send(502, {'error': str(e)})
        elif action == 'export':
            repo = settings(self.root).get('github_repo')
            url = issue_url(repo, (bugs.find(self.root, bug_id) / 'report.md').read_text(encoding='utf-8'))
            if not url:
                return self.send(409, {'error': 'Set the GitHub repo (owner/repo) where bugs go first.'})
            return self.send(200, {'url': url})
        return self.send(200, detail(self.root, bug_id))


def serve(root, live=None, port=PORT):
    """Starts the dashboard in a background thread. Returns (server, url)."""
    handler = type('LensHandler', (Handler,), {'root': Path(root), 'live': live})
    server = ThreadingHTTPServer(('127.0.0.1', port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f'http://127.0.0.1:{server.server_address[1]}/'
