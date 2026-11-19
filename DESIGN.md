---
version: alpha
name: Flight Recorder
description: The Playtest Lens dashboard, a dark instrument a game tester keeps open beside the phone for hours to watch, catch and file bugs.

colors:
  primary: "#ECE7DF"
  secondary: "#968E83"
  tertiary: "#F26A2E"
  neutral: "#1C1A17"
  surface: "#141311"
  raised: "#24221E"
  on-surface: "#D8D2C8"
  border: "#35322C"
  error: "#EE6A62"
  caution: "#E3B648"
  advisory: "#74B9C9"
  normal: "#86AA80"

typography:
  readout:
    fontFamily: IBM Plex Mono
    fontSize: 28px
    fontWeight: 500
    lineHeight: 1.1
    letterSpacing: -0.01em
  headline:
    fontFamily: IBM Plex Sans
    fontSize: 20px
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: -0.01em
  title:
    fontFamily: IBM Plex Sans
    fontSize: 15px
    fontWeight: 600
    lineHeight: 1.35
  body:
    fontFamily: IBM Plex Sans
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.55
  body-sm:
    fontFamily: IBM Plex Sans
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.5
  data:
    fontFamily: IBM Plex Mono
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.45
  log:
    fontFamily: IBM Plex Mono
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: IBM Plex Mono
    fontSize: 11px
    fontWeight: 500
    lineHeight: 1.3
    letterSpacing: 0.12em

rounded:
  none: 0px
  sm: 2px
  md: 4px
  full: 9999px

spacing:
  xxs: 2px
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px
  xxl: 40px

components:
  page:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    typography: "{typography.body}"
  panel:
    backgroundColor: "{colors.neutral}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.lg}"
  panel-title:
    backgroundColor: "{colors.neutral}"
    textColor: "{colors.secondary}"
    typography: "{typography.label}"
  video-frame:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.secondary}"
    rounded: "{rounded.none}"
  timecode:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.primary}"
    typography: "{typography.readout}"
  rec-indicator:
    backgroundColor: "{colors.tertiary}"
    textColor: "{colors.surface}"
    typography: "{typography.label}"
    rounded: "{rounded.full}"
    padding: "{spacing.xs}"
  bug-row:
    backgroundColor: "{colors.neutral}"
    textColor: "{colors.on-surface}"
    typography: "{typography.body-sm}"
    padding: "{spacing.sm}"
  bug-row-selected:
    backgroundColor: "{colors.raised}"
    textColor: "{colors.primary}"
    typography: "{typography.title}"
  chip-crash:
    backgroundColor: "{colors.neutral}"
    textColor: "{colors.error}"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    padding: "{spacing.xxs}"
  chip-perf:
    backgroundColor: "{colors.neutral}"
    textColor: "{colors.caution}"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    padding: "{spacing.xxs}"
  chip-visual:
    backgroundColor: "{colors.neutral}"
    textColor: "{colors.advisory}"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    padding: "{spacing.xxs}"
  chip-manual:
    backgroundColor: "{colors.neutral}"
    textColor: "{colors.primary}"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    padding: "{spacing.xxs}"
  status-ok:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.normal}"
    typography: "{typography.label}"
  button-primary:
    backgroundColor: "{colors.tertiary}"
    textColor: "{colors.surface}"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    padding: "{spacing.sm}"
  button-primary-hover:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
  button-secondary:
    backgroundColor: "{colors.raised}"
    textColor: "{colors.primary}"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    padding: "{spacing.sm}"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.primary}"
    typography: "{typography.body}"
    rounded: "{rounded.sm}"
    padding: "{spacing.sm}"
  input-error:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.error}"
  log-view:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    typography: "{typography.log}"
    padding: "{spacing.md}"
  data-cell:
    backgroundColor: "{colors.neutral}"
    textColor: "{colors.on-surface}"
    typography: "{typography.data}"
  section-heading:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.primary}"
    typography: "{typography.headline}"
  tooltip:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.sm}"
    padding: "{spacing.xs}"
  rule:
    backgroundColor: "{colors.border}"
    textColor: "{colors.primary}"
---

# Flight Recorder

## Overview

Playtest Lens is a dashcam for game testers, and its dashboard is designed as the instrument panel of
a flight data recorder: something that sits quietly, records everything, and only lights up when
there is something to look at. The tester's eyes belong to the phone. The dashboard is glanced at
between rounds and studied only when a bug has been caught, so at rest it must be nearly silent:
warm charcoal, small type, thin rules, and no colour except where state has changed.

The register is precise and serious, an instrument rather than an app. Bug reports, timecodes and
log lines are evidence, and the design treats them like readouts: monospace, aligned, tabular, never
decorated. The one warm gesture is the black-box orange that means "recording" and "caught".

What it gives up: friendliness and first-impression charm. A first-time visitor sees a dense, dark
instrument with tiny tracked labels. That is the trade for a screen that can stay open for an
eight-hour test session without tiring the eye or competing with the game.

## Colors

The palette comes from aviation. The accent is the international orange that flight data recorders
are painted so they can be found in wreckage. Here it marks the same thing: the moment worth
finding. The neutrals are warm cockpit charcoal, not navy. The state colours follow the cockpit
annunciator convention pilots already read without thinking: red is a warning, amber is a caution,
cyan is an advisory, green is normal.

- **Primary (instrument white):** placard white for the text that matters: selected rows, timecodes,
  input text, titles. Slightly warm; never pure white.
- **Secondary (worn placard):** labels, panel titles, metadata, empty states.
- **Tertiary (black-box orange):** the only accent, with one job: *live or caught*. The REC
  indicator, the newest unread catch, the primary action (export or mark bug). Under 5% of pixels.
- **Neutral / Surface / Raised (cockpit charcoal):** three tonal layers that replace shadows: the
  page, panels, and the selected or hovered row.
- **On-surface:** body text on charcoal.
- **Border (panel seam):** 1px rules between panels and rows.
- **Error (master warning):** crashes and ANRs, and invalid input.
- **Caution (master caution):** performance: frame drops, freezes.
- **Advisory (advisory cyan):** visual and text glitches.
- **Normal (normal green):** device connected, buffer healthy. Used only in the status bar.

Severity is shown as coloured chip *text* on charcoal, never as filled colour blocks. A feed full of
red and amber fills would look like a broken cockpit and hide the orange.

## Typography

Two faces from one family, split by classification. **IBM Plex Mono** carries everything that is
evidence or measurement: timecodes, FPS, device IDs, log lines, chip labels, panel titles. **IBM
Plex Sans** carries what a person wrote or reads as prose: bug titles, steps, notes. Plex was drawn
for IBM's engineering heritage and reads as industrial without nostalgia. Both are open source
(SIL OFL) and served from Google Fonts. Fallbacks: `ui-monospace, Menlo, monospace` and
`system-ui, sans-serif`.

The scale is small on purpose (14px body, 11px labels) because this is a dense tool used at arm's
length on a laptop. The large end is a single readout size used for the live timecode and the FPS
gauge. Labels are uppercase Plex Mono, tracked +0.12em. Figures are always tabular
(`font-variant-numeric: tabular-nums`) so timecodes don't jitter as they tick. Two weights only for
emphasis: 400 and 600 (500 is reserved for mono labels and readouts, where Plex Mono's 400 is too
thin at 11px).

## Layout

A fixed three-zone instrument layout on a 4px base:

- **Left, about 40%:** the live device view in a bracketed video frame, with the timecode readout
  and the REC indicator above it and the buffer meter below.
- **Right, about 60%:** the bug feed as a dense list (32px rows) above the selected bug's detail:
  clip player, report editor, and log view, as tabs.
- **Bottom:** a 28px status bar: device, game package, FPS, buffer length, model status.

Layout is asymmetric and stable: panels never move or reflow when bugs arrive. New bugs push into
the top of the feed. Under 1100px wide the device view collapses to a thumbnail above the feed; the
dashboard is a desktop tool and does not target phones. Report text is limited to 72ch.

## Elevation & Depth

Flat. Depth comes from three tonal layers (surface, then neutral panels, then raised for the
selected row) and 1px panel-seam borders. No drop shadows anywhere, except the tooltip and menus,
which float: those get a 0 4px 12px shadow in `rgba(10, 9, 8, 0.6)`, cast straight down.

## Shapes

Hard and small. The video frame has 0 radius and four 12px corner brackets in border colour, like
a viewfinder; when a catch fires, the brackets flash orange for 400ms. Panels use the 4px radius,
chips and buttons 2px. Full radius is reserved for the REC dot and its pill. All borders are 1px in
the border colour; a selected row gets a 2px left bar in instrument white, never in orange.

## Components

- **REC indicator:** an orange dot plus `REC` label, pulsing at 1Hz (opacity 1 to 0.45) only while
  recording. It's the one moving thing on the screen at rest.
- **Bug row:** time (mono), severity chip, one-line title, clip length. The newest unread row has a
  4px orange dot before the time; it clears when opened. Hover and selected rows use the raised
  layer.
- **Severity chips:** `CRASH`, `ANR`, `FREEZE`, `JANK`, `VISUAL`, `TEXT`, `MANUAL`, uppercase mono,
  coloured text on neutral with a 1px border in the same colour at 40% opacity.
- **Mark bug button:** the primary orange button, always visible in the device panel's header and
  labelled with its hotkey (`MARK  F8`).
- **Clip player:** the timeline scrubber shows the catch moment as an orange tick and touches as
  small white ticks. It loops the clip by default.
- **Report editor:** plain inputs on the surface layer; generated text appears in instrument white,
  and fields the tester edited stay that way.
- **Log view:** monospace, line numbers in secondary; the matched lines (the exception, the ANR)
  get a caution-amber left rule.

## Do's and Don'ts

- Do keep orange to one meaning, *live or caught*. If something needs emphasis that isn't a catch
  or the primary action, use instrument white or weight.
- Don't fill rows, panels or banners with severity colour; severity is chip text only.
- Do render every number, time, ID and log line in Plex Mono with tabular figures.
- Don't add drop shadows to panels or cards; depth is tonal layers and seams.
- Don't animate anything at rest except the REC pulse. Transitions are 120ms ease-out or instant;
  no fades on new rows. A new bug appears, it doesn't slide in.
- Do keep the device view's position and size fixed; never let the feed push it around.
- Don't use pure #000 or #FFF, or a navy/slate dark; the charcoal must stay warm.
- Don't add a second accent hue, gradients, glows, or illustrations. Empty states are one line of
  secondary-colour mono text.
- Do show keyboard shortcuts beside actions (`F8`, `J`/`K` to move through bugs, `E` to export);
  testers' hands are on the phone.
- Do give every control a visible focus ring: 2px instrument white, offset 2px. Never orange (that
  would read as a catch), never removed. Tab order follows the zones left to right, top to bottom.
- Do honour `prefers-reduced-motion`: the REC pulse becomes a steady dot and the bracket flash a
  single frame of colour.
- Do show progress for anything slower than about 400ms: the model writing a report or a clip
  being cut shows a mono `WRITING…` / `CUTTING…` line with `aria-busy` in place of the content it
  will replace. Never a spinner over the whole panel.
- Do announce new catches through an `aria-live="polite"` region (`CRASH caught, 14:02:31`), so
  catches are not colour-only or sight-only.
- Do keep body text at 12px or more. 11px is for uppercase mono labels only.
