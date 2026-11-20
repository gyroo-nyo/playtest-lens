"""Text bugs: raw string keys (MENU_START_TITLE), placeholders ({0}, %s) and null/undefined on screen.

Every few seconds Lens takes a full-size frame from the newest video segment and reads it with
macOS Vision (ocr/ocr.swift, compiled once with swiftc; free and offline). Each broken string is
reported once per session.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

from .logcat import Event

SRC = Path(__file__).parent / 'ocr' / 'ocr.swift'
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
    """Path to the compiled reader, building it on first use. None when this Mac can't (no swiftc)."""
    if BIN.exists() and BIN.stat().st_mtime >= SRC.stat().st_mtime:
        return BIN
    if not shutil.which('swiftc'):
        return None
    BIN.parent.mkdir(parents=True, exist_ok=True)
    done = subprocess.run(['swiftc', '-O', str(SRC), '-o', str(BIN)], stdin=subprocess.DEVNULL, capture_output=True)
    return BIN if done.returncode == 0 else None


def read(image):
    """[(text, x, y, w, h)] in 0..1, top-left origin."""
    binary = ocr_binary()
    if not binary:
        return []
    out = subprocess.run([str(binary), str(image)], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30)
    try:
        data = json.loads(out.stdout.splitlines()[0])
    except (IndexError, ValueError):
        return []
    return [(l['text'], l['x'], l['y'], l['w'], l['h']) for l in data['lines']]


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
