# Playtest Lens

**A dashcam for game testers.** Plug in an Android phone and play. Playtest Lens keeps the last 30 seconds of screen, touches and logs, catches crashes and "app not responding" on its own, and lets you mark anything else with one key. Every bug becomes a folder with a clip, the logs, your touches and a report you can paste into Jira or GitHub. Everything runs on your computer, free.

> Status: phases 1–3 of 6 built (recording, five detectors, reports, the dashboard). See [PLAN.md](PLAN.md).

## Try it

You need Python 3.10+, `adb` (Android platform-tools) and `ffmpeg`, and a phone with **USB debugging** on.

```sh
git clone https://github.com/<you>/playtest-lens && cd playtest-lens
python3 -m venv .venv && .venv/bin/pip install -e .
ln -s "$PWD/.venv/bin/lens" ~/.local/bin/lens     # optional: run `lens` from anywhere
lens com.example.game                            # first time: the game's package
lens                                             # after that: the same game again
```

- A crash or ANR is saved automatically, and so is a real freeze (you keep tapping, nothing on screen changes for 3 s and the game stops drawing frames), frame drops (the game stutters under 30 fps), text bugs (raw keys like `MENU_START_TITLE`, `{0}`, `null` on screen) and missing-texture magenta. Clips have an FPS meter in the corner. Wrong catch? Type `x` and Enter.
- **Dashboard:** open http://127.0.0.1:8737 while Lens runs: the phone's screen, the bug feed, clips with your taps on the timeline, reports you can edit, a local-AI draft, and a prefilled GitHub issue. `lens ui` opens it on saved bugs without a phone. It only listens on your own Mac.
- Saw something the detectors missed? Press **Enter** in the terminal (or **F8**, or Mark in the dashboard): the moment is saved right away, the 15-second clip starting 12 seconds *before*. Then type what went wrong whenever you're ready and press Enter; it goes into that bug's report.
- **Discord:** Send to Discord (D) in the dashboard shows the message first, then posts it with a small copy of the clip and the picture through a channel webhook you paste once (channel settings → Integrations → Webhooks). Copy text works without a webhook: it also opens Finder on `discord.mp4`, the clip made small enough to drag into Discord. Nothing is posted unless you press Send.

Each bug lands in `bugs/<time>_<kind>/`: `clip.mp4` (15 s, with your taps shown), `moment.jpg` (the screen at the bug), `report.md`, `logcat.txt`, `touches.jsonl`, `meta.json`.

## Develop

```sh
.venv/bin/pip install -e ".[dev]" && .venv/bin/pytest
```

The tests use recorded crash dumps and touch streams, so no phone is needed. Design system: [DESIGN.md](DESIGN.md).

## License

MIT
