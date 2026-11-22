"""The phone's health while the game runs: the game's memory, CPU/GPU heat, throttling and the battery.
One `adb shell` every 15 s (about 0.7 s of work on the phone), no root. Heat explains lag that the game's code didn't
cause; memory that keeps climbing over a session is a leak.
"""
import re

EVERY = 15                 # seconds between readings
THROTTLE = ['none', 'light', 'moderate', 'severe', 'critical', 'emergency', 'shutdown']   # Android's thermal status 0-6


def command(pid):
    return (f"dumpsys meminfo {pid} | grep -m1 'TOTAL PSS'; dumpsys thermalservice | grep -m3 -E 'Thermal Status|mName=CPU|mName=GPU'; "
            "dumpsys battery | grep -E '^  (level|temperature):'")


def parse(out):
    """{'mem_mb', 'cpu_c', 'gpu_c', 'throttle', 'battery_c', 'battery_pct'} from command()'s output; missing ones are left out."""
    h = {}
    if m := re.search(r'TOTAL PSS:\s+(\d+)', out):
        h['mem_mb'] = round(int(m.group(1)) / 1024)
    if m := re.search(r'Thermal Status:\s*(\d)', out):
        h['throttle'] = int(m.group(1))
    for name, key in (('CPU', 'cpu_c'), ('GPU', 'gpu_c')):
        if m := re.search(rf'mValue=([\d.]+), mType=\d+, mName={name},', out):
            h[key] = round(float(m.group(1)))
    if m := re.search(r'^\s*level:\s*(\d+)', out, re.M):
        h['battery_pct'] = int(m.group(1))
    if m := re.search(r'^\s*temperature:\s*(\d+)', out, re.M):
        h['battery_c'] = round(int(m.group(1)) / 10)
    return h


def at(readings, ts):
    """The reading closest before `ts`, plus how the game's memory changed over the 10 minutes before it.
    readings: [(host ts, health dict)], oldest first."""
    before = [(t, h) for t, h in readings if t <= ts + 1]
    if not before:
        return None
    t_now, now = before[-1]
    out = dict(now)
    old = [h for t, h in before if t <= t_now - 9 * 60 and 'mem_mb' in h]
    if old and 'mem_mb' in now:
        out['mem_change_10min'] = now['mem_mb'] - old[-1]['mem_mb']
    return out


def line(h):
    """'memory 1.8 GB (+300 MB in 10 min) · CPU 62 °C · throttling: moderate · battery 31 °C, 76%'"""
    if not h:
        return ''
    parts = []
    if 'mem_mb' in h:
        mem = f"memory {h['mem_mb'] / 1024:.1f} GB" if h['mem_mb'] >= 1024 else f"memory {h['mem_mb']} MB"
        if abs(h.get('mem_change_10min', 0)) >= 50:
            mem += f" ({h['mem_change_10min']:+d} MB in 10 min)"
        parts.append(mem)
    if 'cpu_c' in h:
        parts.append(f"CPU {h['cpu_c']} °C")
    if h.get('throttle'):
        parts.append(f"throttling: {THROTTLE[min(h['throttle'], 6)]}")
    if 'battery_c' in h:
        parts.append(f"battery {h['battery_c']} °C" + (f", {h['battery_pct']}%" if 'battery_pct' in h else ''))
    return ' · '.join(parts)
