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
    for line in (FX / name).read_text(encoding='utf-8').splitlines():
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
    assert adb.find_touchscreen((FX / 'getevent_pl.txt').read_text(encoding='utf-8')) == ('/dev/input/event2', 1079, 2399)


def test_touches_first_finger_only():
    tr = Tracker(1079, 2399)
    out = [ev for line in (FX / 'touches.txt').read_text(encoding='utf-8').splitlines() for ev in tr.feed(line)]
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
    m = json.loads((folder / 'meta.json').read_text(encoding='utf-8'))
    assert m['kind'] == 'crash' and m['clip'] is False and m['game_version'] == '1.4.2'
    report = (folder / 'report.md').read_text(encoding='utf-8')
    assert '[Crash] java.lang.NullPointerException' in report and 'held the top-centre' in report and '% across' not in report


def test_manual_note_updates_report(tmp_path):
    ev = Event('manual', 1763561000.0)
    meta = {'model': 'Pixel 7', 'android': '15', 'package': PKG, 'game_version': '1.4.2', 'serial': 'X'}
    folder = bugs.write(tmp_path, ev, meta, [], [], lambda out: False)
    first = (folder / 'report.md').read_text(encoding='utf-8')
    assert '[Bug] Marked by tester' in first
    assert 'stopped responding' not in first      # a manual mark isn't a freeze
    ev.note = 'Ball passes through the goalpost'
    bugs.update(folder, ev, meta, [])
    assert '[Bug] Ball passes through the goalpost' in (folder / 'report.md').read_text(encoding='utf-8')


def test_cut_survives_pruned_segments(tmp_path):
    """A segment deleted by pruning mid-cut is skipped, not fatal; no segments at all means no clip."""
    from lens import video
    assert video.cut([], 0, 1, tmp_path / 'a.mp4') is False
    assert video.cut([(str(tmp_path / 'gone.ts'), 0.0, 2.0)], 0, 1, tmp_path / 'b.mp4') is False
    (tmp_path / 'empty.ts').write_bytes(b'')              # a segment the dead stream left at 0 bytes
    assert video.cut([(str(tmp_path / 'empty.ts'), 0.0, 2.0)], 0, 1, tmp_path / 'c.mp4') is False


def test_lost_video_sounds_once_per_outage():
    from lens import alert
    lost = alert.Incident()
    assert [lost.update(b) for b in (False, True, True, True, False, True)] == [False, True, False, False, False, True]


def test_report_says_what_the_tester_pressed(tmp_path):
    ev = Event('manual', 1000.0, note='Ball goes through the player')
    meta = {'model': 'Infinix X6870', 'android': '16', 'package': PKG, 'game_version': '12.7', 'serial': 'X'}
    desc = {'did': [(2.0, 'SWITCH'), (2.4, 'SWITCH'), (5.0, 'DIVE'), (11.6, 'dragged the bottom-left')],
            'summary': 'SWITCH ×2, DIVE, dragged the bottom-left', 'situation': 'FIRST DOWN AND 10 · 2:00 Q2 · DALLAS · 13'}
    (tmp_path / 'moment.jpg').write_bytes(b'x')
    text = bugs.report(ev, meta, [], tmp_path, t0=988.0, clip_seconds=15, desc=desc)
    assert '| On screen | FIRST DOWN AND 10 · 2:00 Q2 · DALLAS · 13 |' in text
    assert '**Pressed in the 15 s before:** SWITCH ×2, DIVE, dragged the bottom-left' in text
    assert '![the moment of the bug](moment.jpg)' in text and 'red box' not in text and '% across' not in text


def test_without_labels_taps_are_named_by_place():
    ev = Event('manual', 1000.0)
    meta = {'model': 'X', 'android': '16', 'package': PKG, 'game_version': '1', 'serial': 'X'}
    taps = [(985.0, {'type': 'down', 'x': 0.1, 'y': 0.1}), (985.1, {'type': 'up', 'x': 0.1, 'y': 0.1}),   # before the clip
            (990.0, {'type': 'down', 'x': 0.9, 'y': 0.8}), (990.1, {'type': 'up', 'x': 0.9, 'y': 0.8})]
    text = bugs.report(ev, meta, taps, None, t0=988.0, clip_seconds=15)
    assert 'tapped the bottom-right' in text and 'tapped the top-left' not in text


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
    (default: the game froze at 1.5 s: no more lines, since Android logs one only when the game hands over a frame).
    Feeds them in time order; returns the events."""
    fps = fps or (lambda t: None if t >= 1.5 else 47.0)
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
    assert glitch.Detector().check(1.0, pink * (n // 200) + grass * (n - n // 200)).kind == 'glitch'   # one player's texture
    hot_pink = bytes([255, 20, 147])          # a real pink jersey isn't missing-texture magenta
    assert glitch.Detector().check(1.0, hot_pink * (n // 10) + grass * (n - n // 10)) is None
    assert glitch.Detector().check(1.0, pink * (n // 5000) + grass * (n - n // 5000)) is None    # a few stray pixels
    det = glitch.Detector()
    det.check(1.0, pink * n)
    assert det.check(5.0, pink * n) is None            # one report, not one every 3 s


def test_dashboard_bug_actions(tmp_path):
    meta = {'model': 'X', 'android': '16', 'package': PKG, 'game_version': '1', 'serial': 'X'}
    folder = bugs.write(tmp_path, Event('manual', 1763561000.0, note='Ball clips through the post'), meta, [], [], lambda out: False)
    bug = folder.name
    [row] = bugs.listing(tmp_path)['bugs']
    assert row['id'] == bug and row['title'] == 'Ball clips through the post' and row['clip'] is False
    for bad in ['../etc', '_false_alarms', '.', '', 'a/b']:
        assert bugs.find(tmp_path, bad) is None
    assert bugs.save_report(tmp_path, bug, '# my words')
    bugs.update(folder, Event('manual', 1763561000.0, note='new note'), meta, [])
    assert (folder / 'report.md').read_text(encoding='utf-8') == '# my words'          # an edit survives a rebuild
    assert bugs.dismiss(tmp_path, bug) and bugs.listing(tmp_path)['bugs'] == []
    assert [r['id'] for r in bugs.listing(tmp_path)['false_alarms']] == [bug]
    assert bugs.restore(tmp_path, bug) and bugs.listing(tmp_path)['bugs'][0]['id'] == bug


def test_ai_draft_goes_into_the_report():
    ev = Event('manual', 1000.0, note='error')
    meta = {'model': 'X', 'android': '16', 'package': PKG, 'game_version': '1', 'serial': 'X'}
    ai = {'title': 'Player passes through the goalpost on a field goal', 'severity': 'minor',
          'steps': ['Start a game', 'Kick a field goal from the 30'], 'actual': 'The ball passes through the post.',
          'expected': 'The ball bounces off the post.'}
    text = bugs.report(ev, meta, [], None, t0=988.0, clip_seconds=15, ai=ai)
    assert text.startswith('# [Bug] Player passes through the goalpost on a field goal')
    assert '## Steps to reproduce\n1. Start a game\n2. Kick a field goal from the 30' in text
    assert 'The ball bounces off the post.' in text and '**Severity (suggested):** minor' in text


def test_only_local_models_write_reports(monkeypatch):
    from lens import writer
    import io
    class R(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): pass
    tags = {'models': [{'name': 'gpt-oss:120b-cloud'}, {'name': 'qwen2.5-coder:7b'}, {'name': 'qwen3:8b'}]}
    monkeypatch.setattr(writer.urllib.request, 'urlopen', lambda *a, **k: R(json.dumps(tags).encode()))
    assert writer.model() == 'qwen3:8b' and writer.models() == ['qwen3:8b', 'qwen2.5-coder:7b']
    tags['models'] = [{'name': 'deepseek-v3.1:671b-cloud'}]
    assert writer.model() is None


def test_dashboard_server(tmp_path):
    import urllib.request, urllib.error
    from lens import ui
    meta = {'model': 'X', 'android': '16', 'package': PKG, 'game_version': '1', 'serial': 'X'}
    folder = bugs.write(tmp_path, Event('manual', 1763561000.0, note='Ball clips through the post'), meta, [], [], lambda out: False)
    (folder / 'clip.mp4').write_bytes(bytes(range(256)) * 4)          # 1024 bytes standing in for a video
    server, url = ui.serve(tmp_path, None, 0)
    try:
        def get(path, headers=None):
            try:
                with urllib.request.urlopen(urllib.request.Request(url + path.lstrip('/'), headers=headers or {})) as r:
                    return r.status, dict(r.headers), r.read()
            except urllib.error.HTTPError as e:
                return e.code, dict(e.headers), e.read()
        def post(path, body=b'{}', headers=None):
            req = urllib.request.Request(url + path.lstrip('/'), body, {'Content-Type': 'application/json', **(headers or {})}, method='POST')
            try:
                with urllib.request.urlopen(req) as r:
                    return r.status, r.read()
            except urllib.error.HTTPError as e:
                return e.code, e.read()
        assert url.startswith('http://127.0.0.1:')
        assert get('/api/state', {'Host': 'evil.example'})[0] == 403                  # DNS rebinding
        assert post(f'/api/bug/{folder.name}/dismiss', headers={'X-Lens': '1', 'Host': 'evil.example'})[0] == 403
        assert b'Playtest Lens' in get('/')[2]
        assert get('/fonts/rajdhani-700.woff2')[0] == 200 and get('/fonts/nope.woff2')[0] == 404   # fonts ship with Lens
        state = json.loads(get('/api/state')[2])
        assert state['live'] is None and state['bugs'][0]['title'] == 'Ball clips through the post'
        code, headers, body = get(f'/files/{folder.name}/clip.mp4', {'Range': 'bytes=100-199'})
        assert code == 206 and headers['Content-Range'] == 'bytes 100-199/1024' and body == (bytes(range(256)) * 4)[100:200]
        assert get(f'/files/{folder.name}/clip.mp4')[0] == 200
        assert get(f'/files/{folder.name}/meta.json')[0] == 404                      # only clips and the picture
        assert get('/files/..%2F..%2Fetc/clip.mp4')[0] == 404
        assert post(f'/api/bug/{folder.name}/dismiss')[0] == 403                      # no page header: another site
        assert post('/api/mark', headers={'X-Lens': '1'})[0] == 409                  # not recording
        assert post(f'/api/bug/{folder.name}/export', headers={'X-Lens': '1'})[0] == 409   # no repo set yet
        assert post('/api/settings', b'{"github_repo": "a b"}', {'X-Lens': '1'})[0] == 400
        assert post('/api/settings', b'{"github_repo": "superfusion/gfl-bugs"}', {'X-Lens': '1'})[0] == 200
        code, body = post(f'/api/bug/{folder.name}/export', headers={'X-Lens': '1'})
        assert code == 200 and json.loads(body)['url'].startswith('https://github.com/superfusion/gfl-bugs/issues/new?title=')
        code, body = post(f'/api/bug/{folder.name}/note', b'{"text": "Ball goes through the left post"}', {'X-Lens': '1'})
        assert code == 200 and json.loads(body)['meta']['title'] == 'Ball goes through the left post'
        assert post(f'/api/bug/{folder.name}/dismiss', headers={'X-Lens': '1'})[0] == 200
        assert json.loads(get('/api/state')[2])['false_alarms'][0]['id'] == folder.name
    finally:
        server.shutdown()


def test_enter_marks_now_and_the_comment_comes_later():
    from lens import marks
    caught, rewrites = [], []
    m = marks.Marks(caught.append, lambda folder, ev, tw, t0: rewrites.append((folder, ev.note)))
    first = m.mark(ts=100.0)                                   # Enter
    assert m.waiting() and m.note('ball went through the post') == 'kept'   # typed while the clip is cut
    assert first.note == 'ball went through the post' and not m.waiting()
    m.saved(first, 'bugs/a', [], 88.0)                        # the folder is written with the comment
    assert rewrites == []
    second = m.mark(ts=200.0)                                  # Enter again: another mark
    m.saved(second, 'bugs/b', [], 188.0)
    assert m.note('kicker froze mid-kick') == 'added' and rewrites == [('bugs/b', 'kicker froze mid-kick')]
    assert m.note('the crowd flickers') == 'new' and len(caught) == 3 and caught[2].note == 'the crowd flickers'
    m.saved(first, 'bugs/a', [], 88.0)                        # an old mark finishing late doesn't steal the latest
    assert m.latest['ev'] is caught[2]


def test_simple_command(monkeypatch, tmp_path):
    from lens import cli
    monkeypatch.setattr(cli, 'BUGS', tmp_path)
    assert cli.simple(['superfusion.gfl']) == ['watch', 'superfusion.gfl']
    assert cli.simple(['ui']) == ['ui'] and cli.simple(['watch', 'a.b', '--no-ui']) == ['watch', 'a.b', '--no-ui']
    import pytest
    with pytest.raises(SystemExit):
        cli.simple([])                                            # no game yet: says how to start
    cli.remember_package('superfusion.gfl')
    assert cli.simple([]) == ['watch', 'superfusion.gfl']
    assert cli.simple(['--port', '8738']) == ['watch', 'superfusion.gfl', '--port', '8738']


def test_discord_message_and_send(tmp_path):
    from lens import discord, ui
    meta = {'model': 'Infinix X6870', 'android': '16', 'package': PKG, 'game_version': '1.2', 'serial': 'X'}
    folder = bugs.write(tmp_path, Event('manual', 1763561000.0, note='Kicker freezes mid-kick'), meta, [], [], lambda out: False)
    (folder / 'describe.json').write_text(json.dumps({'did': [], 'summary': 'DIVE ×5', 'situation': 'SECOND DOWN AND 11'}), encoding='utf-8')
    assert discord.message(folder) == 'Kicker freezes mid-kick'           # the way GFL bugs go out: the explanation
    text = discord.message(folder, details=True)
    assert text.startswith('**[') and 'Kicker freezes mid-kick' in text and 'SECOND DOWN AND 11' in text and len(text) <= 2000
    (folder / 'moment.jpg').write_bytes(b'\xff\xd8jpeg')
    hook = 'https://discord.com/api/webhooks/123/abc-DEF_9'
    assert discord.valid(hook) and not discord.valid('https://evil.example/api/webhooks/1/x')
    sent = []
    out = discord.send(hook, folder, lambda url, body, kind: sent.append((url, body, kind)) or (200, b'{}'))
    url, body, kind = sent[0]
    assert url == hook + '?wait=true' and kind.startswith('multipart/form-data') and b'Kicker freezes' in body and b'moment.jpg' in body
    assert out['files'] == ['moment.jpg'] and (folder / 'discord.json').exists()
    import pytest
    with pytest.raises(ValueError):
        discord.send(hook, folder, lambda *a: (404, b''))
    import shutil, subprocess as sp
    if shutil.which('ffmpeg'):                                         # the clip made small for pasting by hand
        sp.run(['ffmpeg', '-nostdin', '-loglevel', 'fatal', '-f', 'lavfi', '-i', 'testsrc=size=1920x1080:rate=30:duration=1',
                '-pix_fmt', 'yuv420p', str(folder / 'clip.mp4')], check=True)
        assert discord.small_clip(folder).name == 'clip.mp4'              # fits in 20 MB: sent as it is
        import unittest.mock as mock
        with mock.patch.object(discord, 'LIMIT', 1024 * 1024 + 10):       # too big: re-encoded to fit
            small = discord.small_clip(folder)
        assert small.name == 'discord.mp4' and small.stat().st_size < discord.LIMIT
        (folder / 'full.mp4').write_bytes((folder / 'clip.mp4').read_bytes())
        assert discord.small_clip(folder, 'full.mp4').name == 'full.mp4'  # the 30 s before, not the 15 s clip
    ui.save_settings(tmp_path, discord_webhook=hook)
    assert ui.public(tmp_path) == {'discord': True}                    # the page never sees the webhook


def test_ocr_reader_per_os(monkeypatch):
    from lens import text
    monkeypatch.setattr(text.sys, 'platform', 'win32')
    monkeypatch.setattr(text.shutil, 'which', lambda n: r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' if n == 'powershell' else None)
    cmd = text.ocr_binary()
    assert cmd[0].endswith('powershell.exe') and cmd[-1] == str(text.PS1) and text.PS1.exists()
    monkeypatch.setattr(text.sys, 'platform', 'linux')
    assert text.ocr_binary() is None
    one = {'text': 'DIVE', 'x': .1, 'y': .2, 'w': .3, 'h': .04}
    assert text.boxes({'lines': [one, one]}) == [('DIVE', .1, .2, .3, .04)] * 2
    assert text.boxes({'lines': one}) == [('DIVE', .1, .2, .3, .04)]          # PowerShell's one-line list
    assert text.boxes({'lines': None}) == []


def test_tracker_second_finger_taps_while_thumb_held():
    """GFL: the thumb stays on the joystick (slot 0) while the other hand taps JUMP (slot 1)."""
    lines = """[  1.000000] EV_ABS       ABS_MT_SLOT          00000000
[  1.000000] EV_ABS       ABS_MT_TRACKING_ID   00000010
[  1.000000] EV_ABS       ABS_MT_POSITION_X    00000064
[  1.000000] EV_ABS       ABS_MT_POSITION_Y    00000064
[  1.000000] EV_SYN       SYN_REPORT           00000000
[  1.100000] EV_ABS       ABS_MT_POSITION_X    00000070
[  1.100000] EV_ABS       ABS_MT_SLOT          00000001
[  1.100000] EV_ABS       ABS_MT_TRACKING_ID   00000011
[  1.100000] EV_ABS       ABS_MT_POSITION_X    00000300
[  1.100000] EV_ABS       ABS_MT_POSITION_Y    00000600
[  1.100000] EV_SYN       SYN_REPORT           00000000
[  1.200000] EV_ABS       ABS_MT_TRACKING_ID   ffffffff
[  1.200000] EV_SYN       SYN_REPORT           00000000
[  1.300000] EV_ABS       ABS_MT_SLOT          00000000
[  1.300000] EV_ABS       ABS_MT_POSITION_Y    00000070
[  1.300000] EV_SYN       SYN_REPORT           00000000""".splitlines()
    tr = Tracker(1079, 2399)
    out = [(e['type'], e['finger']) for line in lines for e in tr.feed(line)]
    assert out == [('down', 0), ('move', 0), ('down', 1), ('up', 1), ('move', 0)]


def test_situation_skips_the_fps_meter():
    from lens.describe import situation
    lines = [('415 FPS', 0.01, 0.01, 0.07, 0.03), ('160 FFS', 0.01, 0.02, 0.07, 0.03), ('60 FPSmmm', 0.01, 0.01, 0.2, 0.03), ('1:25 Q2', 0.4, 0.01, 0.1, 0.03), ('CHICAGO', 0.6, 0.01, 0.1, 0.03)]
    assert situation(lines) == '1:25 Q2 · CHICAGO'
    from lens.describe import no_meter
    assert [no_meter(t) for t in ['59 FPSOWN AND 10', 'f60 FPSS', '60 FP59', '60 FPSIN', '160 FFS', '1:25 Q2', '14']] == \
        ['OWN AND 10', '', '', '', '', '1:25 Q2', '14']


def test_crash_lines_skip_other_apps():
    """A real `am crash` on GFL: other apps' 'libc: Access denied' lines in the same seconds aren't part of it."""
    from lens.logcat import Detector, parse
    raw = """1795332489.881 27599 27599 E AndroidRuntime: FATAL EXCEPTION: main
1795332489.881 27599 27599 E AndroidRuntime: Process: superfusion.gfl, PID: 27599
1795332489.881 27599 27599 E AndroidRuntime: android.app.RemoteServiceException$CrashedByAdbException: shell-induced crash
1795332490.182 18662 18662 W libc    : Access denied finding property "qemu.hw.mainkeys"
1795332491.606  2750  2799 W libc    : Access denied finding property "ro.odm.tr_game.controller.feature.support"
1795332489.882 27599 27599 I ExceptionHandle: at android.os.Looper.loop(Looper.java:440)""".splitlines()
    d, ev = Detector('superfusion.gfl'), None
    for line in raw:
        e = parse(line)
        ev = d.feed(e, e.ts, {27599}) or ev
    assert ev.kind == 'crash' and len(ev.lines) == 4 and not any('libc' in l for l in ev.lines)


def _freeze_run(fps_after=None, taps=(11.0, 12.0, 13.0, 14.0), away=False, moving=False):
    """GFL with the thumb held on the joystick; at 10 s the picture stops. Frames arrive like Android's screen
    recorder sends them: 5 a second while the picture changes, afterwards only when a tap dot appears or goes,
    and Lens ticks 4 times a second in between. fps_after: the game's frame rate after 10 s (None: no lines)."""
    import random
    from lens import freeze
    W, H = freeze.W, freeze.H

    def frame(seed, dot=None):
        r = random.Random(seed)
        b = bytearray(r.randrange(40, 200) for _ in range(W * H))
        if dot:
            cx, cy = int(dot[0] * W), int(dot[1] * H)
            for y in range(cy - 3, cy + 4):
                for x in range(cx - 3, cx + 4):
                    b[y * W + x] = 255
        return bytes(b)

    d, out, still = freeze.Detector(), [], frame(10)
    d.touch(0.0, {'type': 'down', 'x': 0.15, 'y': 0.8})
    events = [(round(i * 0.2, 2), 'f', frame(i)) for i in range(50)]
    if away:     # an ad opens over the game at 10 s and sits still
        events.append((10.0, 'open', 'com.google.android.gms/.ads.AdActivity'))
    events += [(float(s), 'fps', 58.0) for s in range(10)]
    if fps_after == 'on_taps':     # real, 22 Nov: still play-calling screen, the game draws a frame per tap (1.4-1.6 fps)
        events += [(12.63, 'fps', 1.62), (14.02, 'fps', 1.43)]
    elif fps_after is not None:
        events += [(float(s), 'fps', fps_after) for s in range(10, 20)]
    for t in taps:
        events += [(t, 'down', None), (t + 0.02, 'f', frame(10, (0.8, 0.75))), (t + 0.1, 'up', None), (t + 0.12, 'f', still)]
    if moving:   # the picture keeps changing (a replay, a cut-scene): frames keep coming
        events += [(round(10 + i * 0.2, 2), 'f', frame(1000 + i)) for i in range(50)]
    events += [(round(10 + i * 0.25, 2), 'tick', None) for i in range(40)]
    for ts, kind, x in sorted(events, key=lambda e: e[0]):
        if kind == 'f':
            ev = d.frame(ts, x)
        elif kind == 'tick':
            ev = d.tick(ts)
        elif kind == 'fps':
            ev = d.drawing(ts, x)
        elif kind == 'open':
            ev = d.opened(x, 'superfusion.gfl')
        else:
            ev = d.touch(ts, {'type': kind, 'x': 0.8, 'y': 0.75})
        if ev:
            out.append(ev)
    return out


def test_freeze_caught_when_the_recorder_sends_no_frames():
    out = _freeze_run()
    assert len(out) == 1 and out[0].kind == 'freeze' and 11 <= out[0].ts <= 12


def test_no_freeze_on_a_still_screen_the_game_still_draws():
    assert _freeze_run(fps_after=58.0) == []        # GFL's pre-snap screen: still picture, game drawing


def test_no_freeze_on_a_still_screen_that_draws_only_when_tapped():
    assert _freeze_run(fps_after='on_taps', taps=(12.0, 13.23, 14.61)) == []


def test_no_freeze_while_an_ad_is_on_top():
    assert _freeze_run(away=True) == []


def test_no_freeze_while_the_picture_moves():
    assert _freeze_run(moving=True) == []


def test_no_freeze_with_too_few_taps():
    assert _freeze_run(taps=(11.0, 12.5)) == []


def test_delete_old_bugs(tmp_path, monkeypatch):
    import time as t
    now = t.mktime(t.strptime('2026-11-22 13:00:00', '%Y-%m-%d %H:%M:%S'))
    for name in ['20261110-090000_manual', '20261121-235900_crash', '20261122-080000_manual', '20261122-125930_manual',
                 '_false_alarms/20261101-100000_freeze', '_false_alarms/20261122-090000_lag']:
        (tmp_path / name).mkdir(parents=True)
        (tmp_path / name / 'meta.json').write_text('{}')
    (tmp_path / '.lens.json').write_text('{}')
    names = lambda when: sorted(f.name for f in bugs.older(tmp_path, when, now))
    assert names('week') == ['20261101-100000_freeze', '20261110-090000_manual']
    assert names('today') == ['20261101-100000_freeze', '20261110-090000_manual', '20261121-235900_crash']
    assert '20261122-125930_manual' not in names('all') and len(names('all')) == 5   # saved 30 s ago: maybe still writing
    monkeypatch.setattr('sys.platform', 'linux')      # plain delete: tests must not fill the real Trash
    gone = bugs.trash(bugs.older(tmp_path, 'week', now))
    assert len(gone) == 2 and not (tmp_path / '20261110-090000_manual').exists() and (tmp_path / '.lens.json').exists()



# Real lines from the Infinix X6870 (GFL's saved logs, 21-22 Nov)
REAL_SWIPE = '1795331676.065  3595  3687 I rms_SwipeUpCleanPolicy:  kill proc pid: 1890,uid 10465 proc: superfusion.gfl'
REAL_REMOVE = '1795331676.085  2750  2799 I ActivityManager: Killing 1890:superfusion.gfl/u0a465 (adj 700): remove task'
REAL_EXIT = '1795331784.197 27009  8663 I superfusion.gfl: System.exit called, status: 0'
REAL_DIED = '1795331784.514  2750  2799 I ActivityManager: Process superfusion.gfl (pid 27009) has died: fg  TOP '
REAL_MEMORY_FOR_LAUNCH = '1795284683.096  3595  3652 I rms_NormalReclaimer: doFastKill: , package: superfusion.gfl, uid: 10465, gap: 1057.2MB'


def _gone(lines, crash_at=None):
    from lens import gone
    d, out = gone.Detector('superfusion.gfl'), []
    for line in lines:
        e = logcat.parse(line)
        if crash_at is not None and e.ts >= crash_at:
            d.crash(crash_at)
            crash_at = None
        if (ev := d.feed(e, e.ts, {27009})):
            out.append(ev)
    return out


def test_game_closed_on_screen():
    [ev] = _gone([REAL_DIED])
    assert ev.kind == 'closed' and 'while on screen' in ev.lines[0]


def test_games_own_clean_exit_is_not_a_bug():
    assert _gone([REAL_EXIT, REAL_DIED]) == []          # 22 Nov 12:46: GFL called System.exit(0), reopened 15 s later


def test_exit_with_an_error_code_is_a_bug():
    assert len(_gone([REAL_EXIT.replace('status: 0', 'status: 1'), REAL_DIED])) == 1


def test_swiping_the_game_away_is_not_a_bug():
    assert _gone([REAL_SWIPE, REAL_REMOVE, REAL_DIED.replace('1795331784.514', '1795331676.1')]) == []


def test_a_crash_is_not_also_a_closed_game():
    assert _gone([REAL_DIED], crash_at=1795331760.0) == []


def test_background_death_and_memory_for_launch_are_not_bugs():
    assert _gone([REAL_MEMORY_FOR_LAUNCH, REAL_DIED.replace('fg  TOP ', 'cch  CEM ')]) == []


REAL_HEALTH = """           TOTAL PSS:  1816042            TOTAL RSS:  1157449       TOTAL SWAP PSS:   749940
Thermal Status: 2
	Temperature{mValue=60.182, mType=0, mName=CPU, mStatus=0}
	Temperature{mValue=58.4, mType=1, mName=GPU, mStatus=0}
  level: 76
  temperature: 301
"""


def test_phone_health_from_real_output():
    from lens import health
    h = health.parse(REAL_HEALTH)
    assert h == {'mem_mb': 1773, 'throttle': 2, 'cpu_c': 60, 'gpu_c': 58, 'battery_pct': 76, 'battery_c': 30}
    readings = [(0.0, {**h, 'mem_mb': 1400}), (300.0, {**h, 'mem_mb': 1600}), (600.0, h)]
    now = health.at(readings, 605.0)
    assert now['mem_change_10min'] == 373
    assert health.line(now) == 'memory 1.7 GB (+373 MB in 10 min) · CPU 60 °C · throttling: moderate · battery 30 °C, 76%'
    assert health.parse('') == {} and health.at([], 5.0) is None and health.line(None) == ''


def test_bug_keeps_its_health_reading_when_a_note_arrives(tmp_path):
    meta = {'model': 'X', 'android': '16', 'package': PKG, 'game_version': '1', 'serial': 'X'}
    from lens import health
    ev = Event('manual', 1763561000.0)
    folder = bugs.write(tmp_path, ev, {**meta, 'health': health.parse(REAL_HEALTH)}, [], [], lambda out: False)
    assert '| Phone | memory 1.7 GB' in (folder / 'report.md').read_text()
    ev.note = 'kicker fell short'
    bugs.update(folder, ev, meta, [], False)              # the note arrives later, with the plain session meta
    assert json.loads((folder / 'meta.json').read_text())['health']['mem_mb'] == 1773
    assert '| Phone | memory 1.7 GB' in (folder / 'report.md').read_text()


def test_regression_checks(tmp_path):
    from lens import checks
    data = checks.load(tmp_path)
    a = checks.add(data, '  Open the controls editor:   no lag ')
    b = checks.add(data, 'Kick a 40-yard field goal')
    assert a['text'] == 'Open the controls editor: no lag' and b['id'] == 2
    assert checks.add(data, 'Kick a 40-yard field goal') is None and checks.add(data, '   ') is None
    checks.result(data, '12.8.21X', 1, 'pass')
    checks.result(data, '12.8.22X', 1, 'fail')
    checks.result(data, '12.8.22X', 2, 'pass')
    checks.result(data, '12.8.22X', 2, None)              # changed my mind: not checked
    assert checks.report(data, '12.8.22X') == 'Build 12.8.22X: 0 passed, 1 failed, 1 not checked\n❌ Open the controls editor: no lag'
    checks.save(tmp_path, data)
    again = checks.load(tmp_path)
    assert again['runs']['12.8.21X'] == {'1': 'pass'} and again['last_build'] == '12.8.22X'
    checks.remove(again, 1)
    assert [c['id'] for c in again['checks']] == [2]
