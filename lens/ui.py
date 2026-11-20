"""The dashboard: a local web page for the bug feed, clips, reports and (while `lens watch` runs) the live phone.

Standard library only. Binds to 127.0.0.1: clips can show private chats and games under NDA, so
nothing else on the network may reach it. Serves files only from inside the bugs folder, supports
HTTP Range so Safari can play and seek the clips, answers only requests addressed to 127.0.0.1 or
localhost (no DNS rebinding), and only accepts actions sent with the page's own header.
"""
import json
import mimetypes
import re
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import bugs, discord

PAGE = Path(__file__).parent / 'web' / 'index.html'
FILES = {'clip.mp4', 'full.mp4', 'moment.jpg'}
PUBLIC = ('github_repo', 'package')   # settings the page may see; the Discord webhook is a secret
PORT = 8737


class Live:
    """What `lens watch` shares with the page. Without it the page shows the saved bugs only."""

    def __init__(self, package, version, model, mark):
        self.package, self.version, self.model, self.mark = package, version, model, mark
        self.started = time.time()
        self.fps = None
        self.fps_ts = 0.0
        self.frame = None          # path of the latest full-size frame
        self.frame_ts = 0.0
        self.connected = True
        self.caught = []           # (ts, kind, title) of this session's catches, newest last
        self.note = None           # add_note(text): the comment for the latest mark
        self.marks = None          # marks.Marks: which mark is waiting for a comment

    def state(self):
        now = time.time()
        return {'package': self.package, 'version': self.version, 'model': self.model, 'connected': self.connected,
                'fps': self.fps if now - self.fps_ts < 3 else None, 'recording_for': round(now - self.started),
                'frame_ts': self.frame_ts, 'caught': self.caught[-20:], 'waiting_note': self.waiting_note()}

    def waiting_note(self):
        return self.marks.waiting() if self.marks else None


def settings_path(root):
    return Path(root) / '.lens.json'


def settings(root):
    try:
        return json.loads(settings_path(root).read_text())
    except (OSError, ValueError):
        return {}


def public(root):
    s = settings(root)
    return {**{k: s[k] for k in PUBLIC if k in s}, 'discord': bool(s.get('discord_webhook'))}


def save_settings(root, **changes):
    s = {**settings(root), **changes}
    settings_path(root).parent.mkdir(parents=True, exist_ok=True)
    settings_path(root).write_text(json.dumps(s, indent=2))
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
    m = json.loads((folder / 'meta.json').read_text())
    read = lambda name: (folder / name).read_text() if (folder / name).exists() else None
    t0 = m.get('clip_start')
    ev_ts = time.mktime(time.strptime(m['time'], '%Y-%m-%d %H:%M:%S')) if m.get('time') else None
    taps = []
    if t0 is not None and (folder / 'touches.jsonl').exists():
        for line in (folder / 'touches.jsonl').read_text().splitlines():
            t = json.loads(line)
            if t.get('type') == 'down' and t['host_ts'] >= t0:
                taps.append(round(t['host_ts'] - t0, 2))
    log = (read('logcat.txt') or '').splitlines()[-400:]
    matched = set(m.get('matched_lines') or [])
    return {
        'id': bug_id, 'false_alarm': folder.parent.name == bugs.FALSE, 'meta': m,
        'report': read('report.md') or '', 'edited': (folder / 'report.edited.md').exists(),
        'describe': json.loads(read('describe.json') or 'null'), 'ai': json.loads(read('ai.json') or 'null'),
        'files': sorted(n for n in FILES if (folder / n).exists()),
        'discord': json.loads(read('discord.json') or 'null'),
        'bug_at': round(ev_ts - t0, 2) if ev_ts and t0 is not None else None, 'taps': taps,
        'log': [{'text': l, 'hit': any(x and x in l for x in matched)} for l in log],
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
        if m := re.fullmatch(r'/api/bug/([^/]+)', path):
            d = detail(self.root, urllib.parse.unquote(m.group(1)))
            return self.send(200 if d else 404, d)
        if m := re.fullmatch(r'/files/([^/]+)/([^/]+)', path):
            folder, name = bugs.find(self.root, urllib.parse.unquote(m.group(1))), m.group(2)
            if not folder or name not in FILES or not (folder / name).exists():
                return self.send(404, {'error': 'no such file'})
            return self.file(folder / name, mimetypes.guess_type(name)[0] or 'application/octet-stream')
        if path == '/live.jpg':
            frame = self.live and self.live.frame
            if not frame or not Path(frame).exists():
                return self.send(404, {'error': 'no live frame'})
            return self.file(Path(frame), 'image/jpeg')
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
        m = re.fullmatch(r'/api/bug/([^/]+)/(report|dismiss|restore|rebuild|ai|export|discord|discord-text)', path)
        if not m:
            return self.send(404, {'error': 'not found'})
        bug_id, action = urllib.parse.unquote(m.group(1)), m.group(2)
        if not bugs.find(self.root, bug_id):
            return self.send(404, {'error': 'no such bug'})
        if action == 'report':
            bugs.save_report(self.root, bug_id, str(body.get('text', '')))
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
            return self.send(200, {'text': discord.message(bugs.find(self.root, bug_id))})
        elif action == 'discord':
            hook = settings(self.root).get('discord_webhook')
            if not hook:
                return self.send(409, {'error': 'Paste the channel\'s Discord webhook link first.'})
            try:
                discord.send(hook, bugs.find(self.root, bug_id))
            except ValueError as e:
                return self.send(502, {'error': str(e)})
        elif action == 'export':
            repo = settings(self.root).get('github_repo')
            url = issue_url(repo, (bugs.find(self.root, bug_id) / 'report.md').read_text())
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
