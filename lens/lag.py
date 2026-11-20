"""Frame drops: the game keeps drawing, but slowly.

Uses the game's own frame rate from the log (see freeze.game_fps), about one reading a second.
GFL normally draws 45-60 fps, but its play-calling screen draws a steady 15 fps on purpose. So
slow alone is not lag: a drop is SLOW_FOR readings in a row under SLOW fps WITH a stutter (a frame
that took HITCH ms or more). Readings near 0 are left to the freeze detector (paused or frozen).
"""
from .logcat import Event

SLOW = 30.0        # fps under this is visible lag
SLOW_FOR = 2       # readings in a row (about seconds)
STOPPED = 2.0      # under this the game isn't drawing at all: not lag
HITCH = 250.0      # ms: a frame this long is a visible stutter (steady 15 fps menus peak ~120)
COOLDOWN = 15.0    # one report per laggy stretch


class Detector:
    def __init__(self):
        self.run = []              # (ts, fps) of the current slow stretch
        self.quiet_until = 0.0

    def drawing(self, ts, fps, longest):
        """Feed one reading (fps, longest frame in ms); returns an Event('lag') or None."""
        if fps < STOPPED or fps >= SLOW or longest < HITCH:
            self.run = []
            return None
        self.run.append((ts, fps, longest))
        if len(self.run) < SLOW_FOR or ts < self.quiet_until:
            return None
        first, worst = self.run[0][0], min(f for _, f, _ in self.run)
        hitch = max(m for _, _, m in self.run)
        self.quiet_until = ts + COOLDOWN
        self.run = []
        return Event('lag', first, lines=[f'Frame drops: the game fell to {worst:.0f} fps (normally 45-60) and one frame took {hitch / 1000:.1f} s'])
