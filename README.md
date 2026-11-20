# Playtest Lens

**A dashcam for game testers.** Plug in an Android phone and play. Playtest Lens keeps the last 30 seconds of screen, touches and logs, catches crashes and "app not responding" on its own, and lets you mark anything else with one key. Every bug becomes a folder with a clip, the logs, your touches and a report you can paste into Jira or GitHub. Everything runs on your computer, free.

> Status: phase 1 of 6 (recording, crash catching, manual marks). See [PLAN.md](PLAN.md).

## Try it

You need Python 3.10+, `adb` (Android platform-tools) and `ffmpeg`, and a phone with **USB debugging** on.

```sh
git clone https://github.com/<you>/playtest-lens && cd playtest-lens
python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/lens devices
.venv/bin/lens watch com.example.game
```

- A crash or ANR is saved automatically, and so is a real freeze (you keep tapping, nothing on screen changes for 3 s and the game stops drawing frames). Wrong catch? Type `x` and Enter.
- Saw something the detectors missed? Press **F8** (fn+F8 on a Mac; the terminal needs Accessibility permission), or type `m <what happened>` and Enter. The 15-second clip starts 12 seconds *before* you pressed.

Each bug lands in `bugs/<time>_<kind>/`: `clip.mp4` (15 s, with your taps shown), `step1.jpg…` (where you tapped), `report.md`, `logcat.txt`, `touches.jsonl`, `meta.json`.

## Develop

```sh
.venv/bin/pip install -e ".[dev]" && .venv/bin/pytest
```

The tests use recorded crash dumps and touch streams, so no phone is needed. Design system: [DESIGN.md](DESIGN.md).

## License

MIT
