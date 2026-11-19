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

## Rules

- $0 to run; on-device models only. Anything paid is optional and off by default.
- Nothing leaves the machine except reports the user exports.
- **Public demos use an open-source Android game**, never footage of games under a tester NDA.
- Logic lives in the core package with tests; the dashboard only displays it.
- No AI co-author or contributor lines in commits.
