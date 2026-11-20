"""Manual marks: Enter marks now, the comment can come any time later.

The clip comes from the buffer, so the mark has to be instant; typing what went wrong takes a
while. The comment goes to the latest mark that has none: kept on the event until its folder is
written, or written into the report straight away if the folder already exists.
"""
import threading
import time

from .logcat import Event


class Marks:
    def __init__(self, catch, rewrite):
        """catch(ev) saves a bug; rewrite(folder, ev, touches, t0) rewrites its report."""
        self.catch, self.rewrite = catch, rewrite
        self.latest = {'ev': None, 'folder': None, 'touches': [], 't0': None}
        self.lock = threading.Lock()

    def mark(self, note='', ts=None):
        ev = Event('manual', ts or time.time(), note=note)
        with self.lock:
            self.latest = {'ev': ev, 'folder': None, 'touches': [], 't0': None}
        self.catch(ev)
        return ev

    def saved(self, ev, folder, touches, t0):
        """The bug's folder exists now. A comment typed while it was being cut is already on ev."""
        with self.lock:
            if self.latest['ev'] is ev:
                self.latest.update(folder=folder, touches=touches, t0=t0)

    def note(self, text):
        """Returns 'added' (into the saved report), 'kept' (the clip isn't saved yet) or 'new' (a new mark)."""
        with self.lock:
            m = dict(self.latest)
            ev = m['ev']
            if ev and not ev.note:
                ev.note = text
        if not ev or ev.note != text:
            self.mark(text)
            return 'new'
        if m['folder']:
            self.rewrite(m['folder'], ev, m['touches'], m['t0'])
            return 'added'
        return 'kept'

    def waiting(self):
        """The latest mark's time ('14:02:31') while it has no comment, else None."""
        ev = self.latest['ev']
        return time.strftime('%H:%M:%S', time.localtime(ev.ts)) if ev and not ev.note else None
