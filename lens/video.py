"""The video dashcam: phone screen → 2 s segments on disk, and clips cut from them."""
import os
import subprocess
import threading
from pathlib import Path

SEG_SECONDS = 2


def created(st):
    # shortcut: Linux has no birth time, so a segment's start is estimated from its end
    return getattr(st, 'st_birthtime', None) or (st.st_ctime if os.name == 'nt' else st.st_mtime - SEG_SECONDS)


class Recorder(threading.Thread):
    def __init__(self, serial, folder, keep=20):
        super().__init__(daemon=True)
        self.serial, self.dir, self.keep = serial, Path(folder), keep
        self.dir.mkdir(parents=True, exist_ok=True)
        self.stopped = threading.Event()
        self.procs = []

    def run(self):
        n = 0
        while not self.stopped.is_set():
            adb = ['adb', *(['-s', self.serial] if self.serial else [])]
            # screenrecord stops itself after 3 minutes, so restart it every 170 s
            sr = subprocess.Popen([*adb, 'exec-out', 'screenrecord', '--output-format=h264',
                                   '--time-limit', '170', '--bit-rate', '6000000', '-'], stdout=subprocess.PIPE)
            ff = subprocess.Popen(['ffmpeg', '-loglevel', 'error', '-use_wallclock_as_timestamps', '1', '-f', 'h264', '-i', 'pipe:0',
                                   '-an', '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'zerolatency', '-pix_fmt', 'yuv420p',
                                   '-force_key_frames', 'expr:gte(t,n_forced*1)',
                                   '-f', 'segment', '-segment_time', str(SEG_SECONDS), '-reset_timestamps', '1',
                                   '-segment_start_number', str(n), str(self.dir / 'seg%06d.ts')], stdin=sr.stdout)
            sr.stdout.close()
            self.procs = [sr, ff]
            ff.wait()
            n = max((int(p.stem[3:]) for p in self.dir.glob('seg*.ts')), default=n) + 1
            self.prune()

    def segments(self):
        """[(path, start, end)] in host time."""
        segs = []
        for p in self.dir.glob('seg*.ts'):
            st = p.stat()
            segs.append((str(p), created(st), st.st_mtime))
        return segs

    def prune(self):
        for p in sorted(self.dir.glob('seg*.ts'), key=lambda p: p.stat().st_mtime)[:-self.keep]:
            p.unlink(missing_ok=True)

    def stop(self):
        self.stopped.set()
        for p in self.procs:
            p.terminate()


def cut(segments, t0, t1, out):
    """Join the segments and trim to [t0, t1]. Returns False when there is no video."""
    if not segments:
        return False
    listing = Path(out).with_suffix('.txt')
    listing.write_text(''.join(f"file '{Path(s[0]).resolve()}'\n" for s in segments))
    start = max(0.0, t0 - segments[0][1])
    ok = subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(listing),
                         '-ss', f'{start:.2f}', '-t', f'{t1 - t0:.2f}', '-c', 'copy', '-movflags', '+faststart', str(out)]).returncode == 0
    listing.unlink(missing_ok=True)
    return ok
