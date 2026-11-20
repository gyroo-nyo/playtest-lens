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
| Freeze | video + `getevent` + `logcat` | 3+ taps, the **whole** screen unchanged for 3 s (Show-taps dots ignored) **and** the game's own frame rate (BufferQueueProducer `queueBuffer: fps=` for its surface) under 2 fps. Video alone flagged GFL's pre-snap screen. No frame-rate log on a phone = no auto freeze reports. Stuck buttons are left to manual marks (a dead spot and a broken button look the same). `x` + Enter files a wrong catch under `bugs/_false_alarms/` |
| Frame drops | `logcat` (BufferQueueProducer `queueBuffer: fps= … max=` for the game's surface) | 2+ readings in a row under 30 fps **with a stutter** (a frame ≥ 250 ms). GFL's play-calling screen runs a steady 15 fps on purpose, so slow alone isn't lag. Replayed on 452 real readings: one catch, the 3.2 s hitch opening the controls editor |
| Visual glitch | the full-size frame the text check takes every 3 s (game in front and drawing) | ≥ 4% of the screen solid missing-texture magenta. Black is not checked: GFL goes black on purpose (loading, play calling, lock screen). 1,120 real frames: 0 hits. A vision-model confirm can come later, once there's a real positive example |
| Text bug | macOS Vision OCR (`lens/ocr/ocr.swift`, built once with swiftc) or Windows' built-in OCR (`lens/ocr/ocr.ps1`, Windows.Media.Ocr through PowerShell 5.1) on a full-size frame every 3 s, only while the game is on screen and drawing | raw string keys (`MENU_START_TITLE`), unfilled placeholders (`{0}`, `%s`), `null`/`undefined`/`NaN`, `#MISSING`/`???`; each string once per session. 265 real GFL frames: no false hits (the only hits were a WhatsApp chat, now skipped). Cut-off text: later |
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
- Export: Discord (a channel webhook, the tester presses Send after a preview; the clip re-encoded under 10 MB), Markdown, GitHub issue (prefilled page); Jira later
- You edit it before export; nothing is sent anywhere unless you export it

## Replay

Touches are recorded from `adb shell getevent` with timestamps and replayed with `sendevent` (or
`input tap/swipe` as a fallback), starting from the same screen. "Reproduced 3/3" goes in the report.

## Stack

- **Core:** Python 3.12, adb (no root), ffmpeg, macOS Vision or Windows OCR for text (a small Swift or PowerShell helper), `pynput` for the hotkey. All text files and process output are read and written as UTF-8, so Windows code pages never garble logs or notes
- **Video:** `adb exec-out screenrecord` (or scrcpy) piped through ffmpeg into a segmented ring buffer
- **Models:** Ollama on the Mac for report drafts (cloud models skipped); Whisper for voice notes later
- **Dashboard:** standard-library `http.server` + one HTML page (`lens/web/index.html`, no build step, no new packages) on 127.0.0.1:8737: live view, bug feed, clip player with tap ticks, report editor, log view, export. Chosen over FastAPI + React to keep it $0, offline and dependency-free
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
- **Manual mark:** Enter in the terminal, F8 anywhere (pynput global hotkey) or Mark in the dashboard
  marks at once; the next line typed is that mark's comment, before or after its clip is saved (`lens/marks.py`).
- **On a catch or mark:** wait for the "after" (3 s, plus the segment still being written), then write
  `bugs/<time>_<kind>/` with `clip.mp4` (-12 s/+3 s, cut from the segments, with Android's "Show taps" dots and an FPS meter in the top-left from the game's frame-rate log), `moment.jpg` (the frame at the bug), `describe.json` (each tap named by the text under the finger, read with Vision: `DIVE ×5, SWITCH ×5`; drags and holds; the scoreboard along the top: `SECOND DOWN AND 11 · 1:45 Q2 · DALLAS · 13`), `logcat.txt` (60 s
  before + 3 s after), `touches.jsonl`, `meta.json` (device, Android version, game version, kind,
  matched lines, note), and `report.md` (what happened, what's on screen, the picture, what the tester pressed; `bugs.rebuild()` regenerates it from the folder).
- **Late marks:** a manual mark also saves `full.mp4`, the 30 s before it, for when F8 came late.
- **Robustness:** adb streams restart after the phone drops off USB; the recorder waits for an
  authorized phone and restarts after a rotation; no subprocess reads the terminal, so typed notes
  reach Lens.
- **Tests (no phone needed):** log parsing and crash grouping on real crash dumps (Java, native,
  Unity, ANR), getevent parsing and scaling, ring-buffer trimming, picking segments for a time
  window, and bug folder writing.
- **Done when:** with a phone plugged in, force-stopping the game with a crash and pressing F8 each
  produce a bug folder with a playable clip covering the moment.

## Phase 3 design (the dashboard)

`lens watch <package>` serves it at http://127.0.0.1:8737; `lens ui` opens it on saved bugs with no phone.

- **Device panel:** the phone's screen (a frame a second), REC, session clock, FPS, Mark (F8) with a note.
- **Feed:** caught bugs and false alarms, newest first; short notes show the scoreboard beside them.
- **Bug:** what was on screen and what was pressed; Clip (15 s clip or the 30 s before, a scrubber with
  tap ticks and the bug in orange, the picture at the bug), Report (editable Markdown; edits survive a
  rebuild, and an AI draft asks before replacing them), Log (matched lines marked).
- **Actions:** Send to Discord (preview dialog, webhook kept in the gitignored `bugs/.lens.json` and never sent to the page), Open GitHub issue (a prefilled new-issue page on the repo you set; nothing is posted, clips are
  attached by hand), Copy Markdown, False alarm. Each manual bug has a "What went wrong" box: that text is the Discord message and the title.
- **Safety:** 127.0.0.1 only, and only requests addressed to it (no DNS rebinding); files only from inside `bugs/`; POSTs need the page's `X-Lens` header; HTTP
  Range so Safari plays clips.
- **Done when** (still to check on the phone): a catch shows up in the feed live, and goes to a GitHub issue
  in under 30 s.

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
