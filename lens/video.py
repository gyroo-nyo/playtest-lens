"""The video dashcam: phone screen → 2 s segments on disk, and clips cut from them."""
import os
import subprocess
import threading
import time
from pathlib import Path

SEG_SECONDS = 2


def created(st):
    # shortcut: Linux has no birth time, so a segment's start is estimated from its end
    return getattr(st, 'st_birthtime', None) or (st.st_ctime if os.name == 'nt' else st.st_mtime - SEG_SECONDS)


class Recorder(threading.Thread):
    def __init__(self, serial, folder, keep=25, on_frame=None):
        super().__init__(daemon=True)
        self.serial, self.dir, self.keep, self.on_frame = serial, Path(folder), keep, on_frame
        self.dir.mkdir(parents=True, exist_ok=True)
        self.stopped = threading.Event()
        self.procs = []
        self.connected = True

    def ready(self, adb):
        """The phone is connected and has allowed USB debugging (not 'unauthorized' or 'authorizing')."""
        try:
            return subprocess.run([*adb, 'get-state'], stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding='utf-8', timeout=5).stdout.strip() == 'device'
        except subprocess.TimeoutExpired:
            return False

    def run(self):
        n, waiting, paused = 0, False, False
        while not self.stopped.is_set():
            adb = ['adb', *(['-s', self.serial] if self.serial else [])]
            # Before the phone allows USB debugging (or after the cable drops), screenrecord fails at once:
            # wait quietly instead of restarting it in a loop that floods the terminal with errors.
            if not self.ready(adb):
                if not waiting:
                    print('Phone not connected (cable dropped, or USB debugging not allowed yet). Waiting for it…', flush=True)
                    self.connected = False
                    waiting = True
                self.stopped.wait(2)
                continue
            if waiting:
                print('Phone back, recording again.', flush=True)
                self.connected = True
                waiting = False
            began = time.monotonic()
            # screenrecord stops itself after 3 minutes, so restart it every 170 s
            sr = subprocess.Popen([*adb, 'exec-out', 'screenrecord', '--output-format=h264',
                                   '--time-limit', '170', '--bit-rate', '6000000', '-'], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            ff = subprocess.Popen(['ffmpeg', '-nostdin', '-loglevel', 'error', '-use_wallclock_as_timestamps', '1', '-f', 'h264', '-i', 'pipe:0',
                                   '-an', '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'zerolatency', '-pix_fmt', 'yuv420p',
                                   '-force_key_frames', 'expr:gte(t,n_forced*1)',
                                   '-f', 'segment', '-segment_time', str(SEG_SECONDS), '-reset_timestamps', '1',
                                   '-segment_start_number', str(n), str(self.dir / 'seg%06d.ts'),
                                   # a second output for the detectors: tiny gray frames, 5 a second, on stdout
                                   *(['-vf', 'fps=5,scale=160:90,format=gray', '-f', 'rawvideo', 'pipe:1'] if self.on_frame else [])],
                                  stdin=sr.stdout, stdout=subprocess.PIPE if self.on_frame else None, stderr=subprocess.DEVNULL)
            if self.on_frame:
                threading.Thread(target=self.frames, args=(ff.stdout,), daemon=True).start()
            sr.stdout.close()
            self.procs = [sr, ff]
            code = ff.wait()
            # The stream breaks when the screen rotates (a landscape game opening) or the cable drops.
            # ffmpeg's own errors are a wall of red text, so say it once, plainly, and carry on.
            quick = time.monotonic() - began < 3
            if code != 0 and not self.stopped.is_set():
                if not quick:
                    print('Recording restarted (screen rotated or the stream was interrupted).', flush=True)
                elif not paused:   # fails at once, again and again: say it once
                    print('Recording paused: is the phone screen off or locked? Unlock it and Lens carries on.', flush=True)
                    paused = True
            if not quick:
                paused = False
            n = max((int(p.stem[3:]) for p in self.dir.glob('seg*.ts')), default=n) + 1
            self.prune()
            if time.monotonic() - began < 3:  # died at once (screen off, phone busy): don't spin
                self.stopped.wait(3)

    def frames(self, pipe):
        size = 160 * 90
        while chunk := pipe.read(size):
            if len(chunk) == size:
                self.on_frame(time.time(), chunk)

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

    def restart(self):
        """Start screenrecord again (the loop picks it up), e.g. after the screen turned sideways."""
        for p in self.procs:
            p.terminate()

    def stop(self):
        self.stopped.set()
        for p in self.procs:
            p.terminate()


def last_frame(segments, out):
    """Saves the last frame of the newest finished segment as an image. Returns its host time, or None."""
    done = sorted(segments, key=lambda s: s[2])[:-1]     # the newest one is still being written
    if not done:
        return None
    path, _, end = done[-1]
    ok = subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'fatal', '-y', '-sseof', '-0.3', '-i', path,
                         '-frames:v', '1', str(out)], stdin=subprocess.DEVNULL).returncode == 0
    return end if ok else None


def cut(segments, t0, t1, out, fps=None):
    """Join the segments and trim to [t0, t1]. Returns False when there is no video.
    fps: [(host ts, game fps)] to burn an FPS meter into the top-left corner (re-encodes the clip)."""
    import shutil, tempfile
    # Snapshot the segments first (hard links, so no copying): the recorder prunes old ones
    # while ffmpeg is still reading, which broke clips ("Impossible to open seg…").
    snap = Path(tempfile.mkdtemp(prefix='lens-cut-'))
    kept = []
    for i, seg in enumerate(segments):
        dst = snap / f'{i:04d}.ts'
        try:
            os.link(seg[0], dst)
        except OSError:
            try:
                shutil.copy(seg[0], dst)
            except OSError:
                continue  # already pruned
        kept.append((dst, seg[1]))
    if not kept:
        shutil.rmtree(snap, ignore_errors=True)
        return False
    listing = snap / 'list.txt'
    listing.write_text(''.join(f"file '{Path(p).as_posix()}'\n" for p, _ in kept), encoding='utf-8')
    start = max(0.0, t0 - kept[0][1])
    # stdin=DEVNULL: ffmpeg reads the terminal for its own keys and would eat the tester's typing.
    cmd = ['ffmpeg', '-loglevel', 'fatal', '-y', '-f', 'concat', '-safe', '0', '-i', str(listing),
           '-ss', f'{start:.2f}', '-t', f'{t1 - t0:.2f}']
    if fps:
        from . import meter
        cmd += ['-f', 'concat', '-safe', '0', '-i', str(meter.write(fps, t0, t1, snap)),
                '-filter_complex', '[1:v]setpts=PTS-STARTPTS[m];[0:v]setpts=PTS-STARTPTS[v];[v][m]overlay=24:24:eof_action=repeat',
                '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23', '-pix_fmt', 'yuv420p']
    else:
        cmd += ['-c', 'copy']
    done = subprocess.run([*cmd, '-movflags', '+faststart', str(out)], stdin=subprocess.DEVNULL)
    shutil.rmtree(snap, ignore_errors=True)
    return done.returncode == 0
