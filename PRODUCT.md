# Product


## Platform

web

## Users

Mobile game testers. First user: a QA tester at Super Fusion Games playtesting GFL (an American-football game, `superfusion.gfl`) on an Android phone plugged into a MacBook. Also built, public and open source, for other testers on other studios' games. They play for hours with the dashboard open beside the phone, glancing over to mark, check and send bugs.

## Product Purpose

A dashcam for game testers. Lens keeps the last 30 seconds of the phone's screen, touches and logs, catches crashes, ANRs, freezes, frame drops, text bugs and missing-texture glitches by itself, and lets the tester mark anything else at once (Enter / F8) and explain it later. Each bug becomes a folder with a clip, a picture of the moment, logs and a report. Success: a bug goes from "that looked wrong" to a message in the team's Discord, with a clip, in under 30 seconds.

## Positioning

The clip starts before the tester reacted: the buffer means the moment is never missed. Lens names what was pressed from the screen itself (DIVE ×5, SWITCH ×2) and reads the scoreboard, so the report says where in the game it happened. Free, local, no account.

## Operating Context

- The dashboard is a local page at http://127.0.0.1:8737, opened by running `lens`; it also works without a phone on saved bugs (`lens ui`).
- The tester reports the way the studio does: a short explanation and the clip, posted in Discord. Details (scoreboard, buttons pressed, device, build) are an option for others.
- Used beside a phone during play, often for hours, on a MacBook screen (window sometimes narrower than full width).

## Capabilities and Constraints

- Live phone view (a frame a second), REC, session clock, FPS; Mark with a comment typed later.
- Bug feed (caught bugs and false alarms), per-bug Video (15 s clip and the 30 s before, tap ticks, the bug moment), editable Report, Log; Send to Discord (preview first; webhook), Copy, GitHub issue (prefilled), False alarm.
- Standard-library server + one HTML page; no build step, no new dependencies. Binds to 127.0.0.1 only.
- $0 to run; nothing leaves the Mac except what the tester sends.
- The local-AI report writer was tried and removed from the dashboard (it cannot watch the clip).

## Brand Commitments

- Name: Playtest Lens (command `lens`).
- Clips can show games under NDA and private chats: public demos use an open-source Android game, never GFL footage.
- Buttons press and spring back (the tester asked for clicky, bouncy controls).

## Evidence on Hand

Real bug folders in `bugs/` (GFL, private: never in public material). Detector numbers in PLAN.md (e.g. 1,120 frames, 0 false glitch hits). No users, testimonials or adoption numbers exist; do not invent any.

## Product Principles

1. The moment is never lost: marking is instant, explaining can wait.
2. The clip is the evidence; everything else supports it.
3. Report the way the team already does; details are an option, not a toll.
4. Calm beside the game: the dashboard must not compete with the phone for attention (the tester's one stated fear for a redesign: too flashy).
5. Local and free: nothing leaves the machine unless the tester sends it.

## Accessibility & Inclusion

Long sessions glancing across: text at comfortable sizes with WCAG AA contrast, visible keyboard focus, full keyboard use (J/K, 1/2/3, D, X, Enter/F8), Reduce Motion respected.
