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
