"""Parse `adb logcat -v epoch` lines and spot crashes and ANRs of one package."""
import re
from dataclasses import dataclass, field

CRASH_TAGS = {'DEBUG'}   # crash_dump writes a native crash's tombstone under its own pid; other apps' libc/AndroidRuntime lines are noise
LINE = re.compile(r'^\s*(\d+\.\d+)\s+(\d+)\s+(\d+)\s+([VDIWEFA])\s+(.*?)\s*: (.*)$')


@dataclass
class Entry:
    ts: float          # device epoch seconds
    pid: int
    level: str
    tag: str
    msg: str
    raw: str


def parse(line):
    m = LINE.match(line.rstrip('\n'))
    if not m:
        return None
    ts, pid, _tid, level, tag, msg = m.groups()
    return Entry(float(ts), int(pid), level, tag, msg, line.rstrip('\n'))


@dataclass
class Event:
    kind: str          # crash | anr | manual
    ts: float          # host time of the first trigger line
    lines: list = field(default_factory=list)
    note: str = ''


def trigger(e, package, pids):
    """The bug kind this line signals for `package`, or None."""
    mine = e.pid in pids
    if e.tag == 'AndroidRuntime' and (('FATAL EXCEPTION' in e.msg and mine) or e.msg.startswith(f'Process: {package},')):
        return 'crash'
    if mine and ('Fatal signal' in e.msg or e.tag == 'CRASH'):              # native / Unity
        return 'crash'
    if e.tag == 'DEBUG' and f'>>> {package} <<<' in e.msg:                  # tombstone header
        return 'crash'
    if e.tag == 'ActivityManager' and e.msg.startswith(f'ANR in {package}'):
        return 'anr'
    return None


class Detector:
    """Feeds parsed lines; returns a new Event on the first trigger line of a bug.
    Trigger lines within `gap` seconds of the last one join the same bug."""

    def __init__(self, package, gap=3.0):
        self.package, self.gap = package, gap
        self.open, self.open_ts = None, 0.0

    def feed(self, e, host_ts, pids):
        kind = trigger(e, self.package, pids)
        if not kind:
            # the stack trace and dump that follow a trigger belong to the same bug
            if self.open and host_ts - self.open_ts <= self.gap and (e.pid in pids or e.tag in CRASH_TAGS):
                self.open.lines.append(e.raw)
            return None
        if self.open and host_ts - self.open_ts <= self.gap:
            self.open.lines.append(e.raw)
            self.open_ts = host_ts
            return None
        self.open, self.open_ts = Event(kind, host_ts, [e.raw]), host_ts
        return self.open


def headline(lines):
    """The most telling line of a crash, for the report title."""
    for raw in lines:
        e = parse(raw)
        msg = e.msg if e else raw
        if re.match(r'^(Caused by: )?[\w.$]+(Exception|Error)\b', msg) or 'Fatal signal' in msg or msg.startswith('ANR in'):
            return msg.strip()
    return (parse(lines[0]).msg if lines and parse(lines[0]) else '').strip()
