"""An alarm when the video feed is lost, so a tester looking at the phone knows marks won't have clips."""
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ALARM = Path(tempfile.gettempdir()) / 'playtest-lens-alarm-4.wav'   # renamed when the sound changes, so the old cached one isn't reused
# A soft falling two-note chime (E5 then A4, each fading out), once: noticeable, not harsh.
TONE = ("(if(lt(mod(t,1.2),0.4),sin(2*PI*659*t)*exp(-6*mod(t,1.2)),0)"
        "+if(between(mod(t,1.2),0.4,1.2),sin(2*PI*440*t)*exp(-4*(mod(t,1.2)-0.4)),0))*0.35")
MAC_FALLBACK = '/System/Library/Sounds/Sosumi.aiff'


def alarm_file():
    """The alarm sound, made once with ffmpeg. None if ffmpeg couldn't make it."""
    if not ALARM.exists():
        subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'fatal', '-y', '-f', 'lavfi', '-i', f"aevalsrc='{TONE}':s=44100:d=1.2",
                        str(ALARM)], stdin=subprocess.DEVNULL, capture_output=True, timeout=10)
    return ALARM if ALARM.exists() else None


def notify(text):
    """A banner on the computer too, for when the dashboard is behind the game window."""
    try:
        if sys.platform == 'darwin':
            subprocess.run(['osascript', '-e', 'on run a', '-e', 'display notification (item 1 of a) with title "Playtest Lens"',
                            '-e', 'end run', text], stdin=subprocess.DEVNULL, capture_output=True, timeout=5)
    except Exception:
        pass


def ding(text=None):
    """Plays the alarm (and shows text as a notification) in the background. Never blocks, never raises."""
    def play():
        try:
            if text:
                notify(text)
            if sys.platform == 'darwin':
                sound = alarm_file()
                subprocess.run(['afplay', '-v', '1', str(sound or MAC_FALLBACK)], stdin=subprocess.DEVNULL, capture_output=True, timeout=10)
            elif sys.platform == 'win32':
                import winsound
                sound = alarm_file()
                if sound:
                    winsound.PlaySound(str(sound), winsound.SND_FILENAME)
                else:
                    winsound.MessageBeep(winsound.MB_ICONHAND)
        except Exception:
            pass
    threading.Thread(target=play, daemon=True).start()


class Incident:
    """Fires once when the feed goes bad and re-arms only after it comes back, so a long outage is one alarm."""

    def __init__(self):
        self.open = False

    def update(self, bad):
        """bad: the feed is lost right now. Returns True exactly when a new outage starts."""
        if bad and not self.open:
            self.open = True
            return True
        if not bad:
            self.open = False
        return False
