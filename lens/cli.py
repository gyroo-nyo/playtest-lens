"""`lens devices` and `lens watch <package>`."""
import argparse
import json
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from pathlib import Path

from . import adb, alert, bugs, freeze, glitch, gone, health, lag, logcat, marks, text, ui, video
from .logcat import Event
from .ring import Ring, segments_for
from .touches import Tracker

BEFORE, AFTER = 12, 3   # a 15 s clip: long enough to see the lead-up, short enough to watch
FULL = 30               # full.mp4 for manual marks: pressing F8 late shouldn't lose the bug


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
                                      stderr=subprocess.DEVNULL, text=True, encoding='utf-8', errors='replace', bufsize=1)
            for line in self.p.stdout:
                self.on_line(time.time(), line)
            self.p.wait()
            self.stopped.wait(2)

    def terminate(self):
        self.stopped.set()
        if self.p:
            self.p.terminate()


def open_page(url, a):
    if not a.no_open:
        webbrowser.open(url)      # the default browser, on macOS, Windows and Linux


def cmd_watch(a):
    # The page first, so it opens even before the phone is plugged in (it shows the saved bugs).
    server = None
    if not a.no_ui:
        try:
            server, url = ui.serve(a.out, None, a.port)
            print(f'Dashboard: {url}', flush=True)
        except OSError:
            url = f'http://127.0.0.1:{a.port}/'
            print(f'Lens is already running: opening its dashboard ({url}).', flush=True)
        open_page(url, a)
    found = adb.devices()
    if not found:
        print('Waiting for the phone: plug it in with USB debugging on (Ctrl+C to stop)…', flush=True)
        try:
            while not (found := adb.devices()):
                time.sleep(2)
        except KeyboardInterrupt:
            sys.exit('Stopped.')
    serial, model = found[0]
    if Path(a.out).resolve() == BUGS:
        remember_package(a.package)
    s = ['-s', serial]
    meta = adb.info(serial, a.package)
    offset = adb.clock_offset(serial)
    print(f'Watching {a.package} {meta["game_version"]} on {model}. Mark a bug: Enter (or {a.hotkey.upper()}), then type what went wrong whenever you\'re ready. Wrong catch? "x" + Enter. Ctrl+C to stop.')

    logs, touches, rates = Ring(60), Ring(60), Ring(60)
    readings = Ring(11 * 60)        # phone health every 15 s: memory, heat, battery (health.py)
    live = ui.Live(a.package, meta['game_version'], model, None)   # what the dashboard shows; mark is set below
    pids = {'set': adb.pids(serial, a.package)}

    def note_pids():
        # every process id the game has had this session (it gets a new one after a crash): the Log tab's "Game only"
        meta['pids'] = sorted(set(meta.get('pids', [])) | pids['set'])[-10:]
    note_pids()
    detector = logcat.Detector(a.package)
    closed = gone.Detector(a.package)
    seen = freeze.Detector()
    slow = lag.Detector()

    looking = threading.Lock()      # frames (recorder thread) and ticks (below) both feed the freeze detector

    def on_frame(ts, data):
        with looking:
            ev = seen.frame(ts, data)
        if ev:
            print(f'\n● {ev.kind.upper()} caught: {bugs.title(ev)}', flush=True)
            catch(ev)

    def touched(ts, ev):
        with looking:
            seen.touch(ts, ev)

    def still_screen():
        # A frozen game sends no new video frames at all, so the freeze check can't wait for one.
        while True:
            time.sleep(freeze.TICK)
            if not (rec.connected and rec.video_ok):
                continue            # no phone or a dead stream: no picture to judge
            with looking:
                ev = seen.tick(time.time())
            if ev:
                print(f'\n● {ev.kind.upper()} caught: {bugs.title(ev)}', flush=True)
                catch(ev)

    rec = video.Recorder(serial, tempfile.mkdtemp(prefix='lens-video-'), on_frame=on_frame)
    rec.start()
    threading.Thread(target=still_screen, daemon=True).start()
    last_auto = {'folder': None}

    def capture(ev):
        # Wait until the segment holding the clip's end is finished, not still being written.
        time.sleep(max(0.0, ev.ts + AFTER + video.SEG_SECONDS + 0.5 - time.time()))
        t0, t1 = ev.ts - BEFORE, ev.ts + AFTER
        tw = touches.window(t0, t1)
        now = {**meta, 'health': health.at(readings.window(ev.ts - 11 * 60, ev.ts + 1), ev.ts)}
        folder = bugs.write(a.out, ev, now, logs.window(ev.ts - 60, t1), tw,
                            lambda out: video.cut(segments_for(rec.segments(), t0, t1), t0, t1, out, rates.window(t0 - 5, t1)), t0, BEFORE + AFTER)
        if ev.kind != 'manual':
            last_auto['folder'] = folder
        if ev.kind == 'manual':
            marked.saved(ev, folder, tw, t0)
            f0 = ev.ts - FULL
            video.cut(segments_for(rec.segments(), f0, t1), f0, t1, folder / 'full.mp4', rates.window(f0 - 5, t1))
            has_clip = (folder / 'clip.mp4').exists()
            bugs.update(folder, ev, now, tw, has_clip, t0, BEFORE + AFTER)   # lists full.mp4, and a comment typed meanwhile
            if not has_clip:
                print('\n● Saved WITHOUT a clip: no video was arriving from the phone. Check the cable.', flush=True)
                if sounds_on():
                    alert.ding('A mark was saved without a clip. Check the cable.')
        print(f'\n● {ev.kind.upper()} saved: {folder}', flush=True)

    def catch(ev):
        live.caught.append((ev.ts, ev.kind, bugs.title(ev)))
        threading.Thread(target=capture, args=(ev,), daemon=True).start()

    def on_log(ts, line):
        e = logcat.parse(line)
        if not e:
            return
        logs.add(e.ts + offset, e.raw)
        if e.tag == 'ActivityTaskManager' and (act := freeze.started(e.msg)):
            with looking:
                seen.opened(act, a.package)
        frames = freeze.game_frames(e.msg, a.package)
        if frames:
            with looking:
                seen.drawing(e.ts + offset, frames[0])
            rates.add(e.ts + offset, frames[0])
            live.fps, live.fps_ts = frames[0], time.time()
            if (dropped := slow.drawing(e.ts + offset, *frames)):
                print(f'\n● LAG caught: {bugs.title(dropped)}', flush=True)
                catch(dropped)
        ev = detector.feed(e, e.ts + offset, pids['set'])
        if ev:
            closed.crash(ev.ts)       # the process dying next is part of this crash
        else:
            ev = closed.feed(e, e.ts + offset, pids['set'])
        if ev:
            print(f'\n● {ev.kind.upper()} caught: {bugs.title(ev)}', flush=True)
            catch(ev)

    def rewrite(folder, ev, tw, t0):
        bugs.update(folder, ev, meta, tw, True, t0, BEFORE + AFTER)

    marked = marks.Marks(catch, rewrite)

    def mark(note=''):
        ev = marked.mark(note)
        when = time.strftime('%H:%M:%S', time.localtime(ev.ts))
        print(f'\n● MARKED {when}: {note}' if note else
              f'\n● MARKED {when}. Type what went wrong + Enter whenever you\'re ready (Enter alone marks another).', flush=True)

    def add_note(text):
        done = marked.note(text)
        if done == 'added':
            print(f'  comment added to {marked.latest["folder"]}', flush=True)
        elif done == 'kept':
            print('  comment kept: it goes in the report as soon as the clip is saved', flush=True)
        else:
            print(f'\n● MARKED {time.strftime("%H:%M:%S")}: {text}', flush=True)

    # The dashboard: the live phone, the bug feed, clips and reports, on this Mac only.
    live.mark, live.note, live.marks = mark, add_note, marked
    if server:
        server.RequestHandlerClass.live = live      # the page switches from saved bugs to the live phone

    lost = alert.Incident()
    sounds_on = lambda: ui.settings(a.out).get('sounds', True)   # "sounds": false in bugs/.lens.json turns them off

    def show_live():
        # the page's connection status, and the lost-video sound
        while True:
            time.sleep(0.5)
            live.connected, live.video = rec.connected, rec.video_ok
            # One sound per outage: the phone dropped off adb, or the video died while the game is in front and
            # drawing (a locked phone or a still home screen sends no frames either, and must not beep).
            now = time.time()
            game_drawing = not seen.away and bool(rates.window(now - 3, now))
            if lost.update(not rec.connected or (not rec.video_ok and game_drawing)):
                print(f'\n● No video from the phone for {video.STALL} s: marks won\'t have clips. Check the cable.', flush=True)
                if sounds_on():
                    alert.ding('No video from the phone: marks won\'t have clips. Check the cable.')
            live.alarm = lost.open
    threading.Thread(target=show_live, daemon=True).start()

    def check_health():
        while True:
            time.sleep(health.EVERY)
            pid = max(pids['set'], default=None)
            if pid and rec.connected:
                if (h := health.parse(adb.shell(serial, health.command(pid)))):
                    readings.add(time.time(), h)
                    live.health = h
    threading.Thread(target=check_health, daemon=True).start()

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
                            lambda t, line: [(touches.add(t, ev), touched(t, ev)) for ev in tracker.feed(line)]))
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
            if line == 'x':
                # A false alarm: kept aside (not deleted) so the detectors can be tuned on it.
                f = last_auto['folder']
                if f and Path(f).exists():
                    dest = Path(a.out) / '_false_alarms' / Path(f).name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    Path(f).rename(dest)
                    last_auto['folder'] = None
                    print(f'  moved to {dest} (false alarm)', flush=True)
                else:
                    print('  nothing to dismiss', flush=True)
            elif line == '' or line == 'm':
                mark()                               # Enter: mark now, comment later
            elif line.startswith('m '):
                mark(line[2:].strip())
            else:
                add_note(line)
    threading.Thread(target=stdin_loop, daemon=True).start()

    def read_screen():
        # Text bugs: read a full-size frame every few seconds (macOS Vision, ~0.3 s a frame).
        words, shot, last = text.Detector(), Path(tempfile.mkdtemp(prefix='lens-ocr-')) / 'frame.png', None
        looks = glitch.Detector()
        reads = bool(text.ocr_binary())     # without it the glitch check still runs: it only needs ffmpeg
        if not reads:
            print('Text-bug check off: needs swiftc on a Mac (Xcode command line tools) or Windows PowerShell.', flush=True)
        while True:
            time.sleep(3)
            try:
                ts = video.last_frame(rec.segments(), shot)
                if ts is None or ts == last:
                    continue
                # Only while the game itself is on screen and drawing: not an ad, WhatsApp or the home screen.
                if seen.away or not rates.window(ts - 2.5, ts + 0.5):
                    continue
                last = ts
                if (ev := looks.check(ts, glitch.small_rgb(shot))):
                    print(f'\n● GLITCH caught: {bugs.title(ev)}', flush=True)
                    catch(ev)
                if reads and (ev := words.check(ts, text.read(shot))):
                    print(f'\n● TEXT caught: {bugs.title(ev)}', flush=True)
                    catch(ev)
            except Exception:
                pass
    threading.Thread(target=read_screen, daemon=True).start()

    try:
        while True:
            time.sleep(2)
            pids['set'] = adb.pids(serial, a.package) or pids['set']   # keep the old pid while it is dying
            note_pids()
            if ts:   # games turn the screen sideways after Lens starts: map taps with the current rotation
                try:
                    r = adb.rotation(serial)
                    # Some phones keep recording a rotated screen in its old shape, as a thin strip
                    # with black bars: start the recording again so it fills the frame.
                    if r % 2 != tracker.rotation % 2:
                        rec.restart()
                    tracker.rotation = r
                except Exception:
                    pass
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


def cmd_ui(a):
    server, url = ui.serve(a.out, None, a.port)
    print(f'Dashboard: {url}  (saved bugs in {a.out}/; Ctrl+C to stop)', flush=True)
    open_page(url, a)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        server.shutdown()


BUGS = Path(__file__).resolve().parent.parent / 'bugs'     # one bugs folder, whichever folder you start from
COMMANDS = {'devices', 'watch', 'ui', '-h', '--help'}


def simple(argv):
    """`lens` alone watches the last game; `lens <package>` watches that one."""
    if not argv or (argv[0].startswith('-') and argv[0] not in COMMANDS):   # `lens` or `lens --port 8738`
        package = ui.settings(BUGS).get('package')
        if not package:
            sys.exit('Which game? Run: lens <package>, e.g. lens superfusion.gfl (next time just: lens)')
        return ['watch', package, *argv]
    if argv[0] not in COMMANDS and '.' in argv[0] and not argv[0].startswith('-'):
        return ['watch', *argv]
    return argv


def remember_package(package):
    s = ui.settings(BUGS)
    if s.get('package') != package:
        BUGS.mkdir(parents=True, exist_ok=True)
        ui.settings_path(BUGS).write_text(json.dumps({**s, 'package': package}, indent=2), encoding='utf-8')


def main(argv=None):
    argv = simple(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(prog='lens', description='A dashcam and bug reporter for game testers. '
                                 'Just run `lens` (the last game) or `lens <package>`.')
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('devices', help='list connected phones').set_defaults(fn=cmd_devices)
    w = sub.add_parser('watch', help='record a game and catch bugs')
    w.add_argument('package', help='the game package, e.g. com.example.game')
    w.add_argument('--out', default=str(BUGS), help=f'where bug folders go (default: {BUGS})')
    w.add_argument('--hotkey', default='<f8>', help='mark hotkey in pynput format (default: <f8>)')
    w.add_argument('--port', type=int, default=ui.PORT, help=f'dashboard port (default: {ui.PORT})')
    w.add_argument('--no-ui', action='store_true', help="don't start the dashboard")
    w.add_argument('--no-open', action='store_true', help="don't open the dashboard in the browser")
    w.set_defaults(fn=cmd_watch)
    u = sub.add_parser('ui', help='open the dashboard on saved bugs (no phone needed)')
    u.add_argument('--out', default=str(BUGS), help=f'the bugs folder (default: {BUGS})')
    u.add_argument('--port', type=int, default=ui.PORT, help=f'port (default: {ui.PORT})')
    u.add_argument('--no-open', action='store_true', help="don't open the browser")
    u.set_defaults(fn=cmd_ui)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == '__main__':
    main()
