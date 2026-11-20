import json
from pathlib import Path

from lens import adb, bugs, freeze, logcat
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
    assert '[Crash] java.lang.NullPointerException' in report and 'held the top-centre' in report and '% across' not in report


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


def test_report_says_what_the_tester_pressed(tmp_path):
    ev = Event('manual', 1000.0, note='Ball goes through the player')
    meta = {'model': 'Infinix X6870', 'android': '16', 'package': PKG, 'game_version': '12.7', 'serial': 'X'}
    desc = {'did': [(2.0, 'SWITCH'), (2.4, 'SWITCH'), (5.0, 'DIVE'), (11.6, 'dragged the bottom-left')],
            'summary': 'SWITCH ×2, DIVE, dragged the bottom-left', 'situation': 'FIRST DOWN AND 10 · 2:00 Q2 · DALLAS · 13'}
    (tmp_path / 'moment.jpg').write_bytes(b'x')
    text = bugs.report(ev, meta, [], tmp_path, t0=988.0, clip_seconds=15, desc=desc)
    assert '| On screen | FIRST DOWN AND 10 · 2:00 Q2 · DALLAS · 13 |' in text
    assert '**SWITCH ×2, DIVE, dragged the bottom-left**' in text
    assert '1. SWITCH ×2 (10 s before the bug)' in text and '3. dragged the bottom-left (at the bug)' in text
    assert '![the moment of the bug](moment.jpg)' in text and 'red box' not in text and '% across' not in text


def test_without_labels_taps_are_named_by_place():
    ev = Event('manual', 1000.0)
    meta = {'model': 'X', 'android': '16', 'package': PKG, 'game_version': '1', 'serial': 'X'}
    taps = [(985.0, {'type': 'down', 'x': 0.1, 'y': 0.1}), (985.1, {'type': 'up', 'x': 0.1, 'y': 0.1}),   # before the clip
            (990.0, {'type': 'down', 'x': 0.9, 'y': 0.8}), (990.1, {'type': 'up', 'x': 0.9, 'y': 0.8})]
    text = bugs.report(ev, meta, taps, None, t0=988.0, clip_seconds=15)
    assert '1. tapped the bottom-right (10 s before the bug)' in text and 'tapped the top-left' not in text


def test_label_snapping():
    from lens import describe
    known = {'SWITCH': 3, 'SWIT': 9, 'FEINT': 13, 'FEIN': 4, 'ISWITCH': 1}
    assert describe.snap('SWIT', known) == 'SWITCH' and describe.snap('ISWITCH', known) == 'SWITCH'
    assert describe.snap('FEINT', known) == 'FEINT' and describe.snap('FEIN', known) == 'FEINT'
    assert describe.label_at([('JUMP', 0.75, 0.68, 0.06, 0.04)], 0.79, 0.72) == 'JUMP'
    assert describe.label_at([('JUMP', 0.75, 0.68, 0.06, 0.04)], 0.2, 0.7) is None



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
            if v is not None:
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


def feed_fps(readings):
    """readings: [(fps, longest frame ms)], one a second."""
    from lens import lag
    det = lag.Detector()
    return [ev for t, (f, m) in enumerate(readings) if (ev := det.drawing(float(t), f, m))]


SMOOTH = (47, 34)


def test_lag_on_slow_stuttering_frames():
    # 23:04:45 on the Infinix: 7.65 fps with a 3.2 s frame, then 10.8 fps with 766 ms
    [ev] = feed_fps([SMOOTH, (7.65, 3211), (10.83, 766), (25.65, 664), SMOOTH])
    assert ev.kind == 'lag' and ev.ts == 1.0 and '8 fps' in ev.lines[0] and '3.2 s' in ev.lines[0]


def test_play_calling_screen_at_a_steady_15_fps_is_not_lag():
    assert feed_fps([SMOOTH] + [(15.26, 117)] * 14 + [(15.27, 133), SMOOTH]) == []


def test_one_slow_second_is_not_lag():
    assert feed_fps([SMOOTH, (24, 400), SMOOTH, SMOOTH]) == []


def test_zero_fps_is_a_pause_not_lag():
    assert feed_fps([SMOOTH, (0.33, 6106), (1.22, 16008), SMOOTH]) == []


def test_one_report_per_laggy_stretch():
    assert len(feed_fps([SMOOTH] + [(20, 300)] * 12 + [SMOOTH])) == 1


def test_coming_back_from_an_ad_is_not_lag():
    # 08:58 on the Infinix: the ad stuttered, then the game's first frame back came 14 s after its last
    assert feed_fps([SMOOTH, (22.64, 283), (3.0, 14100), SMOOTH]) == []


def test_ad_frames_are_not_the_game():
    line = 'queueBuffer: fps=22.64 dur=1015.79 max=283.47 min=16.0'
    assert freeze.game_frames(f'[superfusion.gfl/com.google.android.gms.ads.AdActivity#28659](this:0xb) {line}', 'superfusion.gfl') is None


def test_tapping_a_still_ad_is_not_a_freeze():
    det = freeze.Detector()
    det.drawing(0.0, 47.0)
    act = freeze.started('START u0 {xflg=0x4 cmp=superfusion.gfl/com.google.android.gms.ads.AdActivity (has extras)} with LAUNCH_MULTIPLE')
    det.opened(act, 'superfusion.gfl')
    still = [(t / 5, frame()) for t in range(0, 40)]
    assert play(det, still, [(2.0, 0.9, 0.1), (3.0, 0.9, 0.1), (4.0, 0.9, 0.1)], fps=lambda t: None) == []
    assert freeze.started('START u0 {act=android.intent.action.MAIN flg=0x10200000 cmp=superfusion.gfl/.AndroidLauncher}') == 'superfusion.gfl/.AndroidLauncher'


def test_fps_meter_timeline():
    from lens import meter
    t0 = 100.0
    steps = meter.timeline([(99.5, 47.2), (101.0, 46.8), (102.0, 15.3)], t0, t0 + 8)
    assert [meter.label(f) for _, f in steps] == ['47 FPS', '15 FPS', '-- FPS']   # 46.8 rounds to 47: no change
    assert steps[1][0] == 2.0 and steps[2][0] == 5.0    # "--" once the last reading is over 2.5 s old
    assert meter.color(15) == (240, 70, 60) and meter.color(None) == (150, 150, 150)
    assert meter.ppm('47 FPS', (0, 0, 0)).startswith(b'P6 ')


def test_text_bugs():
    from lens import text
    for broken in ['MENU_START_TITLE', 'Score: {0}', 'Welcome back, %s', 'Coach: null', 'BTN_PLAY', '#MISSING', 'Reward: undefined']:
        assert text.suspicious(broken), broken
    # everything GFL actually shows, read off real frames
    for fine in ['GFL', 'JUMP', 'SWITCH', 'FEINT', 'GO', 'MINUTEMEN', 'SECOND DOWN AND 4', '1:22 Q4', 'FIELD GOAL !',
                 'EXTRA POINT', 'PREVENT', 'PRESSURE', 'BLITZ', 'thumb pad', 'done', 'defaults', 'cancel', 'DALLAS', '14',
                 'NEW ENGLAND', '100%', 'Q&A', '3RD & 10']:
        assert not text.suspicious(fine), fine


def test_each_text_bug_reported_once():
    from lens import text
    det = text.Detector()
    assert det.check(1.0, [('JUMP',), ('MENU_START_TITLE',)]).lines[0].startswith('Broken text on screen: "MENU_START_TITLE"')
    assert det.check(4.0, [('MENU_START_TITLE',)]) is None


def test_situation_is_the_scoreboard_not_the_status_bar():
    from lens import describe
    top = lambda t, x: (t, x, 0.01, 0.1, 0.03)
    assert describe.situation([top('DALLAS', 0.5), top('SECOND DOWN AND 11', 0.0), top('13', 0.6), top('1:45 Q2', 0.3),
                               top('JUMP', 0.8)[:2] + (0.7, 0.05, 0.04)]) == 'SECOND DOWN AND 11 · 1:45 Q2 · DALLAS · 13'
    assert describe.situation([top('08:57 0 0 0 9', 0.0), top('* Ш kB/s', 0.4), top('vowiFi ıІ| → 79•4¾', 0.8)]) == ''


def test_magenta_missing_texture():
    from lens import glitch
    grass, pink = bytes([60, 140, 60]), bytes([255, 0, 255])
    n = glitch.W * glitch.H
    assert glitch.Detector().check(1.0, pink * (n // 10) + grass * (n - n // 10)).kind == 'glitch'
    assert glitch.Detector().check(1.0, pink * (n // 100) + grass * (n - n // 100)) is None   # a pink jersey or logo
    det = glitch.Detector()
    det.check(1.0, pink * n)
    assert det.check(5.0, pink * n) is None            # one report, not one every 3 s
