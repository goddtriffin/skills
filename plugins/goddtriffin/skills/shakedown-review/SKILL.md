---
name: shakedown-review
description: Use when a UI change needs its device review before Todd looks at it, in any project that has a shakedown.toml, or when asked to "review on every device", "run the sweep", or check a UI on all devices, light and dark.
---

# Shakedown review

## Overview

The canonical pattern's UI review (every device, light and dark) without images in the main context.
The tool does the automated checks and packs the screenshots into a few contact sheets; a fresh Sonnet
helper looks at the sheets and answers in text. **The main agent never opens a PNG** and never receives
one: the helper's answer is at most 30 lines of text.

Needs `shakedown` (check `shakedown --version` against the `shakedown = "x.y.z"` in the repo's
`shakedown.toml`; a mismatch prints the install command) and a `[sweep]` section in `shakedown.toml`.

## Procedure

1. **Run the sweep with the pack.** From the repo root: `shakedown sweep --pack` (or the repo's
   `make sweep PACK=1`). Local servers only; never pass `--base` for anything but `http://127.0.0.1:PORT`.
2. **Read only its output.** `ok sweep N shots` or `FAIL sweep K of N shots`, then one line per failing
   shot (`route@device-theme: rule: message`), a `pixels:` line, and `pack: target/shakedown/review`.
   Layout-rule failures and layout shifts are real: fix them (or, if by design, add an ignore with a
   reason in `[layout].ignore` / `data-shakedown-ignore`) and re-run before the review. Pixel changes
   are information, not failures.
3. **Start a fresh Sonnet helper** (`model: "sonnet"`, a new agent, never a reused one) with only the
   pack path and the brief below. Do not describe the change, your fix or your expectations: an agent
   handed a hypothesis confirms it.
4. **Act on the verdict.** `verdict: fix`: fix each line that is a real bug (the helper can be wrong:
   check the route and device it names in code, never by opening the image), re-run from step 1, and
   start another fresh helper. `verdict: pass`: report it with the pack path. Findings you judge
   not to be bugs go to Todd as a list, one line each, with the reason.

## The brief (paste verbatim, with the pack path)

```
You review screenshots of a web UI. Pack: <PACK PATH>
Read manifest.json first: routes, devices, themes, automated findings and pixel changes. Then open each
contact sheet (<route>-<theme>.png). A sheet shows one page in one theme on every device, tiled at one
scale, each tile labelled with its device and size. A tile outlined red already has an automated finding.
Look for what the automated rules miss: text or controls overlapping or touching without breathing room,
a layout that is too busy or crowded, odd or uneven spacing, low contrast or unreadable text (check the
dark theme too), broken or missing images, things that differ between devices where they should not,
awkward wrapping, anything that looks wrong or unfinished. Compare tiles of the same page across devices.
Do not repeat what manifest.json already lists as a finding.
Answer in text only, at most 30 lines, one line per problem, exactly:
<route> <device> <theme>: <problem>
then a last line, exactly `verdict: pass` (nothing wrong) or `verdict: fix` (at least one real problem).
Never return or describe an image beyond what a problem line needs. Do not edit any file.
```

## Notes

- One sheet is one route and one theme, long edge at most 1568 px, so each tile is small: the
  helper judges layout and polish, not pixel detail. For a closer look at one tile, the helper may name
  it in a line and the main agent re-runs `shakedown sweep --routes <route>` with a narrower scope.
- `target/shakedown/sweep/report.html` has every failing and changed shot full size, for Todd.
- Per-frame accounts, devices and themes come from `shakedown.toml`; the skill does not choose them.
- Interactive look for Todd: `shakedown devices serve --target http://127.0.0.1:PORT`.
