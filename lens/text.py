"""Text bugs: raw string keys (MENU_START_TITLE), placeholders ({0}, %s) and null/undefined on screen.

Every few seconds Lens takes a full-size frame from the newest video segment and reads it with
macOS Vision (ocr/ocr.swift, compiled once with swiftc; free and offline). Each broken string is
reported once per session.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .logcat import Event

SRC = Path(__file__).parent / 'ocr' / 'ocr.swift'
PS1 = Path(__file__).parent / 'ocr' / 'ocr.ps1'
BIN = Path.home() / '.cache' / 'playtest-lens' / 'lens-ocr'

CHECKS = [
    (re.compile(r'\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b'), 'a raw string key, not translated text'),
    (re.compile(r'\{\d+\}|\{[a-zA-Z_]+\}|%(?:\d\$)?[sd@]'), 'a placeholder that was never filled in'),
    (re.compile(r'\b(?:null|undefined|NaN|nil)\b'), 'a missing value shown as text'),
    (re.compile(r'#?MISSING|<missing>|\?\?\?', re.I), 'missing text'),
]


def suspicious(text):
    """Why `text` looks broken, or None."""
    for pattern, why in CHECKS:
        if (m := pattern.search(text)):
            return m.group(0), why
    return None


def ocr_binary():
    """The command that runs the reader: Windows' built-in OCR, or macOS Vision (built on first use).
    None when this machine can't (a Mac without swiftc, or another OS)."""
    if sys.platform == 'win32':
        ps = shutil.which('powershell')          # Windows PowerShell 5.1: pwsh 7 can't load the WinRT OCR types
        return [ps, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(PS1)] if ps else None
    if sys.platform != 'darwin':
        return None
    if BIN.exists() and BIN.stat().st_mtime >= SRC.stat().st_mtime:
        return [str(BIN)]
    if not shutil.which('swiftc'):
        return None
    BIN.parent.mkdir(parents=True, exist_ok=True)
    done = subprocess.run(['swiftc', '-O', str(SRC), '-o', str(BIN)], stdin=subprocess.DEVNULL, capture_output=True)
    return [str(BIN)] if done.returncode == 0 else None


def boxes(d):
    """[(text, x, y, w, h)] from one image's JSON. PowerShell writes a one-line list as a bare object."""
    lines = d.get('lines') or []
    return [(l['text'], l['x'], l['y'], l['w'], l['h']) for l in ([lines] if isinstance(lines, dict) else lines)]


def read(image):
    """[(text, x, y, w, h)] in 0..1, top-left origin."""
    binary = ocr_binary()
    if not binary:
        return []
    out = subprocess.run([*binary, str(image)], stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding='utf-8', timeout=30)
    try:
        data = json.loads(out.stdout.splitlines()[0])
    except (IndexError, ValueError):
        return []
    return boxes(data)


class Detector:
    def __init__(self):
        self.reported = set()

    def check(self, ts, lines):
        """lines: [(text, ...)] read off one frame. Returns an Event('text') for a new broken string, or None."""
        for line in lines:
            hit = suspicious(line[0])
            if hit and hit[0] not in self.reported:
                self.reported.add(hit[0])
                return Event('text', ts, lines=[f'Broken text on screen: "{line[0]}" ({hit[1]})'])
        return None


def read_many(images):
    """{path: [(text, x, y, w, h)]} for many images in one run of the reader."""
    binary = ocr_binary()
    if not binary or not images:
        return {}
    out = {}
    for i in range(0, len(images), 50):
        done = subprocess.run([*binary, *map(str, images[i:i + 50])], stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, encoding='utf-8', timeout=120)
        for line in done.stdout.splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            out[d['file']] = boxes(d)
    return out
