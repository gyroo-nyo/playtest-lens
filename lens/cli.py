"""`lens devices` and `lens watch <package>`."""
import argparse
import subprocess
import sys
import tempfile
import threading
import time

from . import adb, bugs, logcat, video
from .logcat import Event
from .ring import Ring, segments_for
from .touches import Tracker

BEFORE, AFTER = 12, 3   # a 15 s clip: long enough to see the lead-up, short enough to watch


def pick_device():
    found = adb.devices()
    if not found:
        sys.exit('No phone found. Plug it in, turn on USB debugging, and accept the prompt on the phone.')
    return found[0]


def cmd_devices(_):
    for serial, model in adb.devices() or [('', 'none: plug in a phone with USB debugging on')]:
        print(f'{serial}  {model}')


class stream:
    """Runs an adb command and hands each output line to `on_line` (host time, line).
    When the phone drops off USB the command dies with it, so it's started again once the phone is back."""

    def __init__(self, args, on_line):
        self.args, self.on_line, self.p, self.stopped = args, on_line, None, threading.Event()
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        while not self.stopped.is_set():
            # stdin=DEVNULL: `adb shell` forwards whatever you type to the phone, which ate the "m <note>" you typed.
            self.p = subprocess.Popen(['adb', *self.args], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                      stderr=subprocess.DEVNULL, text=True, errors='replace', bufsize=1)
            for line in self.p.stdout:
                self.on_line(time.time(), line)
            self.p.wait()
            self.stopped.wait(2)

    def terminate(self):
        self.stopped.set()
        if self.p:
            self.p.terminate()


def cmd_watch(a):
    serial, model = pick_device()
    s = ['-s', serial]
    meta = adb.info(serial, a.package)
    offset = adb.clock_offset(serial)
    print(f'Watching {a.package} {meta["game_version"]} on {model}. Mark a bug: {a.hotkey.upper()} or type "m <note>" + Enter. Ctrl+C to stop.')

    logs, touches = Ring(60), Ring(60)
    pids = {'set': adb.pids(serial, a.package)}
    detector = logcat.Detector(a.package)
    rec = video.Recorder(serial, tempfile.mkdtemp(prefix='lens-video-'))
    rec.start()
    last_mark = {'folder': None, 'ev': None, 't0': None}

    def capture(ev):
        # Wait until the segment holding the clip's end is finished, not still being written.
        time.sleep(max(0.0, ev.ts + AFTER + video.SEG_SECONDS + 0.5 - time.time()))
        t0, t1 = ev.ts - BEFORE, ev.ts + AFTER
        tw = touches.window(t0, t1)
        folder = bugs.write(a.out, ev, meta, logs.window(ev.ts - 60, t1), tw,
                            lambda out: video.cut(segments_for(rec.segments(), t0, t1), t0, t1, out), t0, BEFORE + AFTER)
        if ev.kind == 'manual':
            last_mark.update(folder=folder, ev=ev, touches=tw, t0=t0)
        print(f'\n● {ev.kind.upper()} saved: {folder}', flush=True)

    def catch(ev):
        threading.Thread(target=capture, args=(ev,), daemon=True).start()

    def on_log(ts, line):
        e = logcat.parse(line)
        if not e:
            return
        logs.add(e.ts + offset, e.raw)
        ev = detector.feed(e, e.ts + offset, pids['set'])
        if ev:
            print(f'\n● {ev.kind.upper()} caught: {bugs.title(ev)}', flush=True)
            catch(ev)

    def mark(note=''):
        print(f'\n● MARKED: {note}' if note else '\n● MARKED. Type a one-line note and press Enter (or just Enter).', flush=True)
        catch(Event('manual', time.time(), note=note))

    # Android's "Show taps": white dots in the recording wherever a finger touches, so the clip
    # shows what was tapped. Put back as it was when Lens stops.
    taps_before = adb.shell(serial, 'settings get system show_touches').strip()
    adb.shell(serial, 'settings put system show_touches 1')

    procs = [stream([*s, 'logcat', '-v', 'epoch', '-T', '1'], on_log)]
    ts = adb.find_touchscreen(adb.run(serial, 'shell', 'getevent', '-pl'))
    if ts:
        path, mx, my = ts
        tracker = Tracker(mx, my, adb.rotation(serial))
        procs.append(stream([*s, 'shell', 'getevent', '-lt', path],
                            lambda t, line: (ev := tracker.feed(line)) and touches.add(t, ev)))
    else:
        print('No touchscreen found: bugs will have no touch log.')

    try:
        from pynput import keyboard
        keyboard.GlobalHotKeys({a.hotkey: mark}).start()
    except Exception as err:             # no pynput, or no permission to read keys
        print(f'Hotkey off ({err}). Use "m <note>" + Enter instead.')

    def stdin_loop():
        for line in sys.stdin:
            line = line.strip()
            if line == 'm' or line.startswith('m '):
                mark(line[2:].strip())
            elif line and last_mark['ev'] and not last_mark['ev'].note:
                last_mark['ev'].note = line
                bugs.update(last_mark['folder'], last_mark['ev'], meta, last_mark['touches'], True, last_mark['t0'], BEFORE + AFTER)
                print(f'  note added to {last_mark["folder"]}', flush=True)
    threading.Thread(target=stdin_loop, daemon=True).start()

    try:
        while True:
            time.sleep(2)
            pids['set'] = adb.pids(serial, a.package) or pids['set']   # keep the old pid while it is dying
            rec.prune()
    except KeyboardInterrupt:
        print('\nStopped.')
    finally:
        rec.stop()
        try:
            adb.shell(serial, f"settings put system show_touches {taps_before if taps_before in ('0', '1') else 0}")
        except Exception:
            pass   # phone already unplugged
        for p in procs:
            p.terminate()


def main(argv=None):
    ap = argparse.ArgumentParser(prog='lens', description='A dashcam and bug reporter for game testers.')
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('devices', help='list connected phones').set_defaults(fn=cmd_devices)
    w = sub.add_parser('watch', help='record a game and catch bugs')
    w.add_argument('package', help='the game package, e.g. com.example.game')
    w.add_argument('--out', default='bugs', help='where bug folders go (default: ./bugs)')
    w.add_argument('--hotkey', default='<f8>', help='mark hotkey in pynput format (default: <f8>)')
    w.set_defaults(fn=cmd_watch)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == '__main__':
    main()
