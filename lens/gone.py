"""The game vanished while on screen with no crash line: the 'it just closed' bug.

Android says how a process ended (ActivityManager, every phone):
  `Process <pkg> (pid N) has died: fg  TOP`   -> it was the app on screen
  `Killing N:<pkg>/u0aN (adj N): remove task` -> the tester swiped it away
Not bugs: a crash or ANR (already caught: the death is part of it), the tester swiping it away, a force stop or a new
build being installed, and the game's own clean exit (`System.exit called, status: 0`: GFL quits that way when you back
out of it). A death in the background isn't reported: Android ends background games all the time.
Note: Infinix's `rms_NormalReclaimer: doFastKill ... package: <pkg>` is memory being freed FOR the game as it opens, not a kill.
"""
import re

from .logcat import Event

QUIET = 10.0        # after the tester closed it or the game exited cleanly, the death that follows is expected
AFTER_CRASH = 60.0  # an ANR's process can die a while later, when the tester taps 'Close app'


class Detector:
    def __init__(self, package):
        self.package = package
        self.expected = -1e9       # when the tester closed it, a build was installed, or the game called System.exit(0)
        self.crashed = -1e9        # when Lens last caught a crash or ANR

    def crash(self, ts):
        self.crashed = ts

    def feed(self, e, ts, pids=()):
        """e: a parsed logcat Entry, ts: host time, pids: the game's process ids. Returns an Event('closed') or None."""
        p, msg = self.package, e.msg
        if e.pid in pids and msg.startswith('System.exit called, status: 0'):
            self.expected = ts
            return None
        if p not in msg:
            return None
        if (e.tag.startswith('rms_SwipeUp') or re.search(rf'Killing \d+:{re.escape(p)}/\S+ \(adj -?\d+\): remove task', msg)
                or msg.startswith(f'Force stopping {p} ')):
            self.expected = ts
            return None
        died = re.match(rf'Process {re.escape(p)} \(pid \d+\) has died: (.*)', msg)
        if not died or ts - self.expected <= QUIET or ts - self.crashed <= AFTER_CRASH:
            return None
        state = died.group(1).split()
        if 'TOP' not in state and state[:1] != ['fg']:
            return None
        return Event('closed', ts, lines=['The game closed by itself while on screen: no crash or error in the log', e.raw])
