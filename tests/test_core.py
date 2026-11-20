import json
from pathlib import Path

from lens import adb, bugs, logcat
from lens.logcat import Event
from lens.ring import Ring, segments_for
from lens.touches import Tracker, to_screen

FX = Path(__file__).parent / 'fixtures'
PKG, PIDS = 'superfusion.gfl', {4321}


def run(name, pids=PIDS):
    d, events = logcat.Detector(PKG), []
    for line in (FX / name).read_text().splitlines():
        e = logcat.parse(line)
        ev = e and d.feed(e, e.ts, pids)
        if ev:
            events.append(ev)
    return events


def test_parse_line():
    e = logcat.parse('1763561001.003  4321  4321 E AndroidRuntime: java.lang.NullPointerException: boom')
    assert (e.ts, e.pid, e.level, e.tag, e.msg) == (1763561001.003, 4321, 'E', 'AndroidRuntime', 'java.lang.NullPointerException: boom')
    assert logcat.parse('--------- beginning of crash') is None


def test_java_crash_is_one_bug_with_its_exception():
    [ev] = run('java_crash.log')
    assert ev.kind == 'crash' and ev.ts == 1763561001.001
    assert bugs.title(ev).startswith('java.lang.NullPointerException')


def test_native_and_unity_crash_group_into_one():
    [ev] = run('native_crash.log')
    assert ev.kind == 'crash' and len(ev.lines) == 4
    assert bugs.title(ev).startswith('Fatal signal 11')


def test_native_crash_found_by_tombstone_even_without_pid():
    [ev] = run('native_crash.log', pids=set())
    assert ev.kind == 'crash' and '>>> superfusion.gfl <<<' in ev.lines[0]


def test_anr():
    [ev] = run('anr.log', pids=set())
    assert ev.kind == 'anr' and bugs.title(ev).startswith('ANR in superfusion.gfl')


def test_other_apps_are_ignored():
    assert run('other_app.log') == []


def test_find_touchscreen():
    assert adb.find_touchscreen((FX / 'getevent_pl.txt').read_text()) == ('/dev/input/event2', 1079, 2399)


def test_touches_first_finger_only():
    tr = Tracker(1079, 2399)
    out = [ev for line in (FX / 'touches.txt').read_text().splitlines() if (ev := tr.feed(line))]
    assert [e['type'] for e in out] == ['down', 'move', 'up']
    assert out[0]['x'] == round(0x21c / 1079, 4) and out[0]['y'] == round(0x4b0 / 2399, 4)


def test_rotation_maps_panel_to_screen():
    assert to_screen(.25, .1, 0) == (.25, .1)
    assert to_screen(.25, .1, 1) == (.1, .75)       # landscape game on a portrait panel
    assert to_screen(.25, .1, 3) == (.9, .25)


def test_ring_drops_old_items_and_windows():
    r = Ring(60)
    for t in range(0, 100, 10):
        r.add(t, t)
    assert [i for _, i in r.items] == [30, 40, 50, 60, 70, 80, 90]
    assert [i for _, i in r.window(45, 75)] == [50, 60, 70]


def test_segments_for_window():
    segs = [('c', 4, 6), ('a', 0, 2), ('b', 2, 4), ('d', 6, 8)]
    assert [s[0] for s in segments_for(segs, 3, 5)] == ['b', 'c']
    assert segments_for(segs, 20, 25) == []


def test_bug_folder_and_report(tmp_path):
    [ev] = run('java_crash.log')
    meta = {'model': 'Pixel 7', 'android': '15', 'package': PKG, 'game_version': '1.4.2', 'serial': 'X'}
    touches = [(1, {'t': 1, 'type': 'down', 'x': .5, 'y': .25}), (2, {'t': 2, 'type': 'up', 'x': .5, 'y': .25})]
    folder = bugs.write(tmp_path, ev, meta, [(1, 'log line')], touches, lambda out: False, t0=0)
    assert {p.name for p in folder.iterdir()} == {'logcat.txt', 'touches.jsonl', 'meta.json', 'report.md'}
    m = json.loads((folder / 'meta.json').read_text())
    assert m['kind'] == 'crash' and m['clip'] is False and m['game_version'] == '1.4.2'
    report = (folder / 'report.md').read_text()
    assert '[Crash] java.lang.NullPointerException' in report and 'Tap the spot in the red box' in report and '% across' not in report


def test_manual_note_updates_report(tmp_path):
    ev = Event('manual', 1763561000.0)
    meta = {'model': 'Pixel 7', 'android': '15', 'package': PKG, 'game_version': '1.4.2', 'serial': 'X'}
    folder = bugs.write(tmp_path, ev, meta, [], [], lambda out: False)
    first = (folder / 'report.md').read_text()
    assert '[Bug] Marked by tester' in first
    assert 'stopped responding' not in first      # a manual mark isn't a freeze
    ev.note = 'Ball passes through the goalpost'
    bugs.update(folder, ev, meta, [])
    assert '[Bug] Ball passes through the goalpost' in (folder / 'report.md').read_text()


def test_cut_survives_pruned_segments(tmp_path):
    """A segment deleted by pruning mid-cut is skipped, not fatal; no segments at all means no clip."""
    from lens import video
    assert video.cut([], 0, 1, tmp_path / 'a.mp4') is False
    assert video.cut([(str(tmp_path / 'gone.ts'), 0.0, 2.0)], 0, 1, tmp_path / 'b.mp4') is False


def test_report_steps_are_pictures_not_percentages(tmp_path):
    ev = Event('manual', 1000.0, note='Ball goes through the player')
    meta = {'model': 'Infinix X6870', 'android': '16', 'package': PKG, 'game_version': '12.7', 'serial': 'X'}
    taps = [(985.0, {'type': 'down', 'x': 0.1, 'y': 0.1}),   # before the clip: left out
            (990.0, {'type': 'down', 'x': 0.66, 'y': 0.76}), (990.1, {'type': 'up', 'x': 0.66, 'y': 0.76}),
            (995.5, {'type': 'down', 'x': 0.72, 'y': 0.21})]
    (tmp_path / 'step1.jpg').write_bytes(b'x')
    text = bugs.report(ev, meta, taps, tmp_path, t0=988.0, clip_seconds=15)
    assert '% across' not in text
    assert '1. Tap the spot in the red box (10 s before the bug)' in text and '![step 1](step1.jpg)' in text
    assert '2. Tap the spot in the red box (4 s before the bug)' in text and 'step2.jpg' not in text
    assert '15 s leading up to the bug' in text


# --- freeze / stuck button (lens/freeze.py) ---

from lens import freeze


def frame(shade=50, box=None):
    """A flat gray frame, optionally with a bright box (x0, y0, x1, y1 in pixels) = something on screen."""
    f = bytearray([shade]) * (freeze.W * freeze.H)
    if box:
        x0, y0, x1, y1 = box
        for y in range(y0, y1):
            f[y * freeze.W + x0:y * freeze.W + x1] = bytes([250]) * (x1 - x0)
    return bytes(f)


def play(det, frames, taps, fps=None):
    """frames: [(t, frame)], taps: [(t, x, y)], fps: f(t) -> the game's frame rate each second
    (default: the game froze at 1.5 s). Feeds them in time order; returns the events."""
    fps = fps or (lambda t: 0.0 if t >= 1.5 else 47.0)
    events = []
    feed = [(t, 'tap', (x, y)) for t, x, y in taps] + [(t, 'frame', f) for t, f in frames]
    feed += [(t / 1.0, 'fps', fps(t)) for t in range(0, int(max(t for t, _ in frames)) + 1)]
    for t, kind, v in sorted(feed, key=lambda e: e[0]):
        if kind == 'fps':
            det.drawing(t, v)
        elif kind == 'tap':
            det.touch(t, {'type': 'down', 'x': v[0], 'y': v[1]})
            det.touch(t + 0.05, {'type': 'up', 'x': v[0], 'y': v[1]})
        elif (ev := det.frame(t, v)):
            events.append(ev)
    return events


def test_freeze_when_taps_change_nothing():
    still = [(t / 5, frame()) for t in range(0, 40)]                     # 8 s of the same screen
    taps = [(2.0, 0.2, 0.5), (3.0, 0.8, 0.3), (4.0, 0.5, 0.8)]
    [ev] = play(freeze.Detector(), still, taps)
    assert ev.kind == 'freeze' and ev.ts == 2.0


def test_show_taps_dot_is_not_a_change():
    # the white dot at the finger changes pixels there, which must not count as the game reacting
    frames = [(t / 5, frame(box=(28, 40, 36, 48)) if 2.0 <= t / 5 < 2.3 else frame()) for t in range(0, 40)]
    [ev] = play(freeze.Detector(), frames, [(2.0, 0.2, 0.5), (3.0, 0.8, 0.3), (4.0, 0.5, 0.8)])
    assert ev.kind == 'freeze'


def test_still_screen_while_the_game_draws_is_not_a_freeze():
    # GFL's pre-snap: nothing moves until GO, taps on the field do nothing, but the game draws 47 fps
    still = [(t / 5, frame()) for t in range(0, 40)]
    taps = [(2.0 + i * 0.3, 0.6, 0.4) for i in range(10)]
    assert play(freeze.Detector(), still, taps, fps=lambda t: 47.0) == []


def test_no_frame_rate_log_means_no_freeze_reports():
    still = [(t / 5, frame()) for t in range(0, 40)]
    det = freeze.Detector()
    det.drawing = lambda *a: None          # this phone never logs the game's frame rate
    assert play(det, still, [(2.0, 0.2, 0.5), (3.0, 0.8, 0.3), (4.0, 0.5, 0.8)]) == []


def test_game_fps_from_the_log():
    line = 'queueBuffer: fps=46.29 dur=1015.19 max=33.65 min=15.93'
    assert freeze.game_fps(f'[462ec03 SurfaceView[superfusion.gfl/superfusion.gfl.AndroidLauncher](BLAST)#28198] {line}', 'superfusion.gfl') == 46.29
    assert freeze.game_fps(f'[SurfaceView[com.other/x]] {line}', 'superfusion.gfl') is None


def test_spamming_jump_while_the_game_moves_is_never_a_bug():
    # GFL's JUMP gives no feedback on cooldown, but the players keep running: no bug
    frames = [(t / 5, frame(box=(40 + (t % 10), 20, 80 + (t % 10), 70))) for t in range(0, 50)]
    taps = [(1.0 + i * 0.3, 0.8, 0.7) for i in range(25)]
    assert play(freeze.Detector(), frames, taps) == []


def test_a_couple_of_taps_on_a_quiet_menu_is_not_a_bug():
    still = [(t / 5, frame()) for t in range(0, 40)]
    assert play(freeze.Detector(), still, [(2.0, 0.3, 0.3), (2.5, 0.6, 0.6)]) == []


def test_one_bug_per_stuck_moment():
    still = [(t / 5, frame()) for t in range(0, 60)]
    taps = [(2.0 + i * 0.5, 0.5, 0.5) for i in range(14)]
    assert len(play(freeze.Detector(), still, taps)) == 1


def test_rotation_from_window_manager():
    from lens import adb
    assert adb.parse_rotation('  mCurrentRotation=ROTATION_270 mLastOrientation=0') == 3
    assert adb.parse_rotation('DisplayContent{...} mRotation=1 mAltOrientation=false') == 1
    assert adb.parse_rotation('nothing here') is None
