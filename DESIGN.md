---
name: Bitmap Specimen
description: The Playtest Lens dashboard as a bitmap type specimen, kept open beside the phone for hours to mark, check and send bugs.
colors:
  paper: "#F4F4F1"
  paper-2: "#E8E8E3"
  field: "#FCFCFA"
  ink: "#0A0A0A"
  grey: "#5A5A5A"
  band-grey: "#BDBDBD"
  hair: "#D0D0CA"
  primary: "#3340FF"
  primary-tint: "#E2E4FF"
  error: "#C8102E"
  caution: "#8A5A00"
  caution-bg: "#FFF0C2"
  normal: "#2E7A32"
  advisory: "#1F5F8B"
typography:
  readout:
    fontFamily: "Silkscreen, Courier New, monospace"
    fontSize: "52px"
    fontWeight: 700
    lineHeight: 0.9
    letterSpacing: "-0.04em"
  headline:
    fontFamily: "Silkscreen, Courier New, monospace"
    fontSize: "24px"
    fontWeight: 700
    lineHeight: 1.12
    letterSpacing: "-0.03em"
  band-head:
    fontFamily: "Silkscreen, Courier New, monospace"
    fontSize: "22px"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "-0.01em"
  body:
    fontFamily: "Work Sans, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Work Sans, system-ui, sans-serif"
    fontSize: "11px"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "0.1em"
  button:
    fontFamily: "Work Sans, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "0.06em"
  data:
    fontFamily: "JetBrains Mono, ui-monospace, Menlo, monospace"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.5
rounded:
  none: "0px"
spacing:
  xs: "6px"
  sm: "10px"
  md: "16px"
  lg: "20px"
  xl: "24px"
components:
  button:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.button}"
    rounded: "{rounded.none}"
    padding: "8px 14px"
  button-hover:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "#FFFFFF"
    typography: "{typography.button}"
    rounded: "{rounded.none}"
    padding: "8px 14px"
  button-primary-hover:
    backgroundColor: "{colors.ink}"
    textColor: "#FFFFFF"
  input:
    backgroundColor: "{colors.field}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "9px 10px"
  band:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
    height: "60px"
  band-tab-selected:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    padding: "7px 12px"
  band-tab:
    textColor: "{colors.band-grey}"
    padding: "7px 12px"
  label:
    textColor: "{colors.grey}"
    typography: "{typography.label}"
  list-head:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
    typography: "{typography.band-head}"
    height: "48px"
  feed-row:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    height: "38px"
  feed-row-hover:
    backgroundColor: "{colors.paper-2}"
    textColor: "{colors.ink}"
  feed-row-divider:
    backgroundColor: "{colors.hair}"
    height: "1px"
  feed-row-selected:
    backgroundColor: "{colors.primary-tint}"
    textColor: "{colors.ink}"
  chip-crash:
    textColor: "{colors.error}"
    padding: "4px 6px"
  chip-jank:
    backgroundColor: "{colors.caution-bg}"
    textColor: "{colors.caution}"
    padding: "4px 6px"
  chip-advisory:
    textColor: "{colors.advisory}"
    padding: "4px 6px"
  status-ok:
    textColor: "{colors.normal}"
    typography: "{typography.data}"
  toast:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
    padding: "10px 14px"
  toast-error:
    backgroundColor: "{colors.error}"
    textColor: "#FFFFFF"
---

# Design System: Bitmap Specimen

## Overview

**Creative North Star: "The Bitmap Specimen"**

The dashboard reads like an Emigre bitmap type specimen printed on newsprint. The few things a tester glances at from beside the phone (recording time, FPS, bug counts, the selected bug's title) are set in big pixel numerals and caps. Everything read up close (lists, facts, logs, help text) is plain, crisp sans and mono. Regions are cut apart by thick ink rules, not cards or shadows.

It stays calm beside the game: one blue accent, colour kept for meaning (crash, jank), and no decoration that moves. Density is a working tool's: one-size feed rows, tight facts, no hero space. Fonts ship with the app in `lens/web/fonts` (Silkscreen 400/700, Work Sans variable, JetBrains Mono variable), served by `lens/ui.py` at `/fonts/`; the page makes no external font calls and works offline.

**Key Characteristics:**
- Neutral newsprint paper, ink text, 3px ink rules between regions.
- Black bands with paper-coloured pixel caps: the top bar, the bug list head, dialog heads.
- Pixel face only for glance-at numbers and heads, 22px and up.
- Square corners everywhere.
- One ultramarine accent for selection and the primary action.
- Buttons squish on press and spring back.

## Colors

Black ink on a neutral grey-white paper, one synthetic ultramarine, and signal colours that appear only when something is wrong.

### Primary
- **Specimen Ultramarine** (primary; `--accent` in the code): selection (feed row tint, active view underline, the bug tick on the scrubber, unread dot), the primary button (Mark, Send to Discord, Save), focus outlines, text selection and the caret.
- **Ultramarine Wash** (primary-tint; `--accent-tint` in the code): the selected feed row and the waiting comment field's ring.

### Neutral
- **Newsprint** (paper): the page ground. Cooled on purpose from the reference board's warm #F2F0EB; an earlier warm-cream page read as generic.
- **Newsprint Shade** (paper-2): row hover and the scrubber track.
- **Field White** (field): inputs, the log, the Discord preview.
- **Ink** (ink): text, rules, bands, the phone frame, secondary button borders.
- **Pencil Grey** (grey): labels, times, help text, placeholders.
- **Band Grey** (band-grey): quiet text on black bands (unselected tabs, "newest first").
- **Hairline** (hair): 1px dividers between feed rows; disabled field borders.

### Signal
- **Crash Red** (error): CRASH and ANR chips, error toasts, field errors, FPS under 25.
- **Jank Amber** (caution, on caution-bg): FREEZE and JANK chips, FPS 25 to 39, matched log lines, "Phone disconnected".
- **Advisory Blue** (advisory): TEXT and VISUAL chips.
- **Go Green** (normal): "Phone connected", "Sent" in facts.

### Named Rules
**The Neutral Paper Rule.** Greys stay neutral. No cream, beige or warm paper.

**The One Accent Rule.** Ultramarine means "selected" or "do this". It never decorates, and red/amber never stand in for it.

## Typography

**Display Font:** Silkscreen (with Courier New, monospace)
**Body Font:** Work Sans (with system-ui)
**Data Font:** JetBrains Mono (with ui-monospace, Menlo)

**Character:** A blocky bitmap face for what you read from across the desk, a quiet grotesque for what you read up close, and a mono for anything that is a time, a number, a file or a log.

### Hierarchy
- **Readout** (Silkscreen 700, 52px, line-height 0.9): recording clock and FPS. Bug counts use 40px. At phone width 36px and 30px.
- **Headline** (Silkscreen 700, 24px, uppercase, clamped to 4 lines): the selected bug's title.
- **Band head** (Silkscreen 700, 22px): the bug list head and dialog heads, paper on ink.
- **Logo** (Silkscreen 700, 24px): PLAYTEST LENS in the top band.
- **Section head** (Work Sans 700, 13px, uppercase, 0.12em): plain section strips.
- **Body** (Work Sans 400, 14px, 1.5): feed titles, dialog text, help.
- **Button** (Work Sans 700, 12px, uppercase, 0.06em).
- **Label** (Work Sans 600, 11px, uppercase, 0.1em, grey): captions under readouts, fact names.
- **Data** (JetBrains Mono 400, 12 to 13px): times, clip lengths, facts, log, report editor, status bar. Numbers are tabular site-wide.

### Named Rules
**The 22px Floor Rule.** Silkscreen is used at 22px and up. The only exception is the logo at phone width (12px). Anything smaller is Work Sans or JetBrains Mono.

**The One Row Size Rule.** Feed rows are one type size (14px); rank comes from weight and the kind chip, not size.

## Layout

A full-height grid: 60px top band, content, 30px status bar. The content splits into a left phone column (min 320px, 36%) and a right column. The right column stacks the bug list (min 150px, 34%) over the selected bug. The selected bug splits into media (clip, scrubber, picture at the bug) and an info column (280 to 360px: title, facts, comment, actions).

- The phone frame takes the aspect ratio of the live picture, capped at 56vh, so it is sized to its picture.
- A dot-matrix strip (6px dots) sits under the phone, and only there.
- The left column runs top to bottom: readouts, phone frame, dot strip, comment field, bug counts (straight under the comment), frame-rate bars, keyboard shortcuts.
- Padding is 20px inside regions, 16px at phone width; gaps step 6, 10, 16, 20, 24px.
- Under 1100px: one column, the page scrolls, the feed caps at 320px, keyboard hints in the status bar hide, and the "False alarms" tab shortens to "False".
- Under 640px: logo 12px on two lines, REC and key hints hide, feed rows drop the kind chip, the bug counts and the shortcut list hide. Tabs keep short words.

### Named Rules
**The Three Pixel Rule.** Regions are divided by 3px ink rules, blocks inside a column by 2px ink rules, rows by 1px hairlines. Nothing else separates content.

## Elevation & Depth

Flat. There are no drop shadows. Depth comes from black bands against paper and from thick rules. The only box-shadows are rings: the primary button's double frame (`0 0 0 2px paper, 0 0 0 4px ink`, inverted on the black band) and the waiting comment field's 2px ultramarine-wash ring. Dialogs sit on a 55% ink backdrop.

### Named Rules
**The No Lift Rule.** Nothing floats. A thing that matters gets a black band or a frame, never a shadow.

## Shapes

Square corners everywhere (0px). Borders are ink, 2px on controls, fields, chips and media, 3px on dialogs and region rules. The phone frame carries four 14px corner brackets that turn ultramarine and snap inward when a bug is marked or caught. Small markers (unread dot, REC light) are squares, never circles.

## Components

### Buttons
Square, inked, clicky.
- **Shape:** square, 2px ink border, 8px 14px padding, uppercase Work Sans 700 12px.
- **Default:** paper fill, ink text. Hover inverts to ink fill, paper text.
- **Primary:** ultramarine fill, white text, double frame (paper ring then ink ring). Hover turns ink. One primary per view: Mark in the band, Send to Discord on a bug, the confirming action in a dialog.
- **Press:** every button, tab and view tab scales to 0.94 in 70ms and springs back over 280ms (`cubic-bezier(.34, 1.56, .64, 1)`). Shortcut keys press their button visibly. Mark gets a bigger punch (0.86, 1.07, 1) on use.
- **Disabled:** 40% opacity, no hover change.
- **Key hints:** JetBrains Mono 11px inside the button (`F8`, `D`, `X`).

### Tabs
- **Band tabs** (Bugs / False alarms): band-grey text; selected is a paper block with ink text.
- **View tabs** (Video / Report / Log): uppercase Work Sans 700 13px, grey; selected is ink with a 3px ultramarine underline that slides between tabs (300ms).
- **Clip pick** (15 s clip / 30 s before): selected is an ink block with paper text.

### Feed rows
38px rows: unread square, time (mono, grey), kind chip, title, clip length (mono). Hover paper-2, selected ultramarine wash and bold. New rows slide in from the left with a brief wash.

### Chips
Work Sans 700 11px caps with a 2px border in the text colour. Colour by kind: red for CRASH/ANR, amber on pale amber for FREEZE/JANK, advisory blue for TEXT/VISUAL, ink for MANUAL.

### Inputs
Field white, 2px ink border, square, 9px 10px padding. Focus is a 3px ultramarine outline, 2px offset (site-wide `:focus-visible`). Waiting for a comment: ultramarine border, wash ring, hint text turns ultramarine.

### Black bands
The top band (60px), the bug list head (48px) and dialog heads (52px) are ink with paper-coloured Silkscreen caps. REC is a steady square light, grey when off and paper when recording; it does not blink.

### Phone frame and scrubber
The phone sits in an ink frame with corner brackets; on Mark the brackets snap in and a paper shutter flashes once (380ms). The scrubber under a clip is an 18px paper-2 track with an ink playhead, grey tap ticks and an ultramarine bug tick.

### Frame-rate bars
"Frame rate, last minute": 40 bars, one per 1.5 s poll, in a 72px strip on a 2px ink baseline. Each bar is built from 4px blocks with 2px gaps, so it reads as pixels. Height maps 0 to 60 fps; a dashed hairline marks 30 fps. Bars are ink, amber under 30 fps, red under 20. When nothing is recording the bars hide and a one-line grey mono note shows instead.

### Shortcut list
A two-column list under a 2px ink rule: the key in JetBrains Mono 700 12px, what it does in grey Work Sans 13px (Enter, J / K, 1 2 3, D C, X).

### Dialogs and toasts
Dialogs: paper, 3px ink border, black pixel-caps head, 3px ink rule over the footer, spring in (260ms). Toasts: ink with paper text bottom right, spring up (340ms); errors are red with white text, prefixed "Error".

### Motion
Motion is feedback only: press-and-spring, mark punch, corner snap, row arrival, view enter (220ms fade-up), dialog and toast entry. Reduced Motion removes all animation and transforms, keeping only 120ms colour fades.

## Do's and Don'ts

### Do:
- **Do** set glance-at numbers and band heads in Silkscreen at 22px or more, and everything read up close in Work Sans or JetBrains Mono.
- **Do** separate regions with 3px ink rules and put list and dialog heads in black pixel-caps bands.
- **Do** keep ultramarine (#3340FF) for selection, focus and the single primary action.
- **Do** give every control the press-and-spring, and respect Reduce Motion.
- **Do** self-host every font in `lens/web/fonts`.

### Don't:
- **Don't** warm the paper toward cream or beige; it stays #F4F4F1 with neutral greys.
- **Don't** round corners or add drop shadows.
- **Don't** add halftone, grain or extra motion; the finish review asked for none.
- **Don't** make REC or any status light blink.
- **Don't** use red or amber except for crashes, errors and jank.
- **Don't** load fonts or anything else from the network.
