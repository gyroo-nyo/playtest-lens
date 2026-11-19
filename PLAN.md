# Playtest Lens: plan

A dashcam for game testers. You play; it keeps the last 30 seconds of screen, touches and logs,
catches crashes, freezes, frame drops and visual glitches, and turns each one (or any moment you
mark yourself) into a finished bug report with a clip, logs, device info and steps that it can
replay on the device.

Free to run: adb + local models (Ollama). Works on macOS and Windows. Public portfolio project.

## The loop

```
phone ──adb──▶ capture ──▶ ring buffer (30 s: video, touches, logcat, frame stats)
                               │
              detectors ◀──────┤
              hotkey "mark" ◀──┘
                   │
                   ▼
               bug event ──▶ clip (-20 s / +5 s) + logs + device ──▶ local model writes report
                                                                     ──▶ dashboard / export / replay
```

## What it catches

| Signal | Source | Detector |
|---|---|---|
| Crash | `logcat` | `FATAL EXCEPTION`, native crash / tombstone, Unity `Crash!!!`, process died |
| Not responding | `logcat` | `ANR in <package>` |
| Freeze / hang | video + `getevent` | frame unchanged > 2 s while touches arrive |
| Frame drops | `dumpsys gfxinfo <pkg> framestats` | janky-frame % or FPS under a threshold for > 1 s |
| Visual glitch | video | black / magenta missing textures (pixel stats), then a local vision model to confirm |
| Text bug | OCR on frames | raw string keys (`MENU_START_TITLE`), cut-off text, `null`/`{0}` |
| **Anything else** | **you** | **hotkey or "Mark bug" button + one line of text or voice** |

## Manual marks (bugs the detectors missed)

- Global hotkey (default F8) or the dashboard button marks "now". The clip comes from the buffer, so it
  includes what happened before you pressed.
- Add one line (typed, or spoken and transcribed with local Whisper).
- Same report and replay as an automatic catch.
- Every manual mark is stored as a missed detection; the README tracks "share of bugs caught
  automatically" over time.

## The report

Written by a local model (Ollama) from: your note, the touch log mapped to on-screen labels (OCR),
the log lines around the moment, device + game version.

- Title, severity guess, steps to reproduce, expected vs actual, environment, attachments (clip, logs)
- Export: Markdown, Jira (CSV / API), GitHub issue
- You edit it before export; nothing is sent anywhere unless you export it

## Replay

Touches are recorded from `adb shell getevent` with timestamps and replayed with `sendevent` (or
`input tap/swipe` as a fallback), starting from the same screen. "Reproduced 3/3" goes in the report.

## Stack

- **Core:** Python 3.12, adb (no root), OpenCV, Tesseract or EasyOCR for text, `pynput` for the hotkey
- **Video:** `adb exec-out screenrecord` (or scrcpy) piped through ffmpeg into a segmented ring buffer
- **Models:** Ollama (a small vision model for glitches, a text model for reports), Whisper for voice notes
- **Dashboard:** FastAPI + a React web UI on localhost: live view, bug feed, clip player, report editor
- **Tests:** pytest with recorded fixtures (sample logcat dumps, short clips), so detectors are tested
  without a phone. CI on GitHub Actions.

## Phases

| Phase | Goal | Done when |
|---|---|---|
| 0 | Repo, README, CI, device connect | `lens devices` lists the phone, CI green |
| 1 | Ring buffer + crash/ANR detection + clips + manual mark | a forced crash and an F8 press each save a clip with logs |
| 2 | Freeze, frame-drop, glitch and text detectors | each detector passes its fixture tests |
| 3 | Dashboard + AI-written reports + export | a bug goes from catch to a GitHub issue in under 30 s |
| 4 | Touch recording + replay | a recorded bug reproduces on the device |
| 5 | iOS (via a Mac, logs + video, no replay) and PC games (screen capture) | |
| 6 | Demo video, README numbers, release | |

## Phase 1 design (the useful core)

`lens watch <package>` runs three adb streams into time-stamped ring buffers, watches the log for
crashes, listens for the F8 mark, and writes one folder per bug.

| Stream | Command | Buffer |
|---|---|---|
| Video | `adb exec-out screenrecord --output-format=h264 -` (restarted every 170 s, the tool's 3-minute cap) → ffmpeg re-encodes with a keyframe every second into 2 s `.ts` segments | last 20 segments (40 s) on disk |
| Log | `adb logcat -v epoch` | last 60 s in memory |
| Touches | `adb shell getevent -lt <touchscreen>` → down / move / up in screen pixels | last 60 s in memory |

- **Clock:** everything is stamped in host time. Device log times are converted with an offset
  measured at start (`adb shell date`).
- **Crash detector:** lines from the game's process matching `FATAL EXCEPTION`, `Fatal signal`,
  native crash and tombstone headers, Unity crash lines, `ANR in <package>`, and ActivityManager's
  `Process <package> … has died`. Lines within 3 s of each other are one bug.
- **Manual mark:** F8 anywhere (pynput global hotkey), or `m` + Enter in the terminal. Then it asks
  for a one-line note.
- **On a catch or mark:** wait for the "after" (3 s, plus the segment still being written), then write
  `bugs/<time>_<kind>/` with `clip.mp4` (-12 s/+3 s, cut from the segments, with Android's "Show taps" dots), `step1.jpg…` (the frame at each of the last 5 taps with a red box on the spot), `logcat.txt` (60 s
  before + 3 s after), `touches.jsonl`, `meta.json` (device, Android version, game version, kind,
  matched lines, note), and `report.md` (what happened, the clip, picture steps; AI-written steps come in phase 3).
- **Robustness:** adb streams restart after the phone drops off USB; the recorder waits for an
  authorized phone and restarts after a rotation; no subprocess reads the terminal, so typed notes
  reach Lens.
- **Tests (no phone needed):** log parsing and crash grouping on real crash dumps (Java, native,
  Unity, ANR), getevent parsing and scaling, ring-buffer trimming, picking segments for a time
  window, and bug folder writing.
- **Done when:** with a phone plugged in, force-stopping the game with a crash and pressing F8 each
  produce a bug folder with a playable clip covering the moment.

## Skills used on this project

| Skill | Where |
|---|---|
| ponytail | every coding task: smallest complete change, one check per new logic |
| design-md-planner | DESIGN.md (Flight Recorder), linted clean with the official CLI |
| ui-ux-pro-max | UX rules for the dashboard (focus, reduced motion, live regions, loading), phase 3 |
| impeccable / frontend-design | building and polishing the dashboard, phase 3 |
| engineering:testing-strategy | detector fixtures and accuracy numbers, phases 2–3 |
| code-review | before each push |
| bang-motion / hyperframes | the README demo video, phase 6 |

## Rules

- $0 to run; on-device models only. Anything paid is optional and off by default.
- Nothing leaves the machine except reports the user exports.
- **Public demos use an open-source Android game**, never footage of games under a tester NDA.
- Logic lives in the core package with tests; the dashboard only displays it.
- No AI co-author or contributor lines in commits.
