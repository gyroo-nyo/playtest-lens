"""Thin wrappers over adb. Parsing helpers are pure so tests don't need a phone."""
import re
import subprocess
import time


def run(serial, *args, timeout=15):
    cmd = ['adb', *(['-s', serial] if serial else []), *args]
    try:
        return subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout).stdout
    except subprocess.TimeoutExpired:
        return ''   # the phone stopped answering (cable, sleep): carry on as if it said nothing, never crash Lens


def shell(serial, command):
    return run(serial, 'shell', command).strip()


def devices():
    """[(serial, model)] of connected, authorised devices."""
    out = subprocess.run(['adb', 'devices', '-l'], stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding='utf-8').stdout
    found = []
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == 'device':
            model = next((p.split(':', 1)[1] for p in parts if p.startswith('model:')), '?')
            found.append((parts[0], model))
    return found


def pids(serial, package):
    return {int(p) for p in shell(serial, f'pidof {package}').split() if p.isdigit()}


def clock_offset(serial):
    """Host time minus device time, in seconds."""
    t0 = time.time()
    out = shell(serial, 'date +%s.%N')
    t1 = time.time()
    try:
        device = float(out)
    except ValueError:                      # toybox without %N
        device = float(shell(serial, 'date +%s'))
    return (t0 + t1) / 2 - device


def info(serial, package):
    prop = lambda k: shell(serial, f'getprop {k}')
    version = re.search(r'versionName=(\S+)', shell(serial, f'dumpsys package {package}'))
    return {'model': prop('ro.product.model'), 'android': prop('ro.build.version.release'),
            'package': package, 'game_version': version.group(1) if version else '?', 'serial': serial}


def parse_rotation(dumpsys_window):
    """0-3 from `dumpsys window displays`, or None. Newer Android (16 on Infinix) has no
    SurfaceOrientation in `dumpsys input`, so read the window manager instead."""
    m = re.search(r'mCurrentRotation=ROTATION_(\d+)', dumpsys_window)
    if m:
        return int(m.group(1)) // 90
    m = re.search(r'\bmRotation=(\d)\b', dumpsys_window)
    return int(m.group(1)) if m else None


def rotation(serial):
    r = parse_rotation(shell(serial, 'dumpsys window displays'))
    if r is None:
        m = re.search(r'SurfaceOrientation:\s*(\d)', shell(serial, 'dumpsys input'))
        r = int(m.group(1)) if m else 0
    return r


def find_touchscreen(getevent_pl):
    """From `getevent -pl` output: (device path, max x, max y) of the first multi-touch device."""
    for block in re.split(r'(?=add device \d+: )', getevent_pl):
        path = re.match(r'add device \d+: (\S+)', block)
        mx = re.search(r'ABS_MT_POSITION_X\s*:.*?max (\d+)', block)
        my = re.search(r'ABS_MT_POSITION_Y\s*:.*?max (\d+)', block)
        if path and mx and my:
            return path.group(1), int(mx.group(1)), int(my.group(1))
    return None
