"""The Windows app's entry point: uses the adb and ffmpeg that come with it, and keeps the window open at the end."""
import os
import sys
from pathlib import Path

tools = Path(sys.executable).parent / 'tools'
os.environ['PATH'] = str(tools) + os.pathsep + os.environ.get('PATH', '')

from lens import cli  # noqa: E402

code = 0
try:
    cli.main()
except SystemExit as e:
    code = e.code if isinstance(e.code, int) else 1
    if isinstance(e.code, str):
        print(e.code)
except KeyboardInterrupt:
    pass
if not os.environ.get('LENS_NO_PAUSE'):
    try:
        input('\nPress Enter to close.')
    except (EOFError, KeyboardInterrupt):
        pass
sys.exit(code)
