---
name: ui-mockups
description: Use when the user wants to explore, compare, or decide between UI/UX designs before touching real code — several layouts, color sets, copy formats, flows, or page redesigns side by side, at real device sizes, often over rounds of feedback — or asks for mockups, design variants, or a design review of something not yet built.
---

# UI mockups

## Overview

Build throwaway, self-contained HTML mockups that show many (10+) design variants at once, at real
viewport sizes, beside the live product. The user decides; the mockup only makes the choice cheap.
Work in rounds until every open question is closed.

**Never touch production code during design rounds** unless the user says to implement.

## The mockup file

One self-contained HTML file per round: `v1.html`, `v2.html`, … No build step, no dependencies
beyond an optional web font. Start from `reference/template.html`.

- Work in a scratch directory. Serve it in the background with
  `python3 -m http.server <port> --bind 127.0.0.1`.
- Commit a round's file into the project (e.g. `redesign/mockups/vN.html`) only if the user wants a
  record.
- Seed it from the product's real CSS and design tokens where possible; a hand-copied mockup drifts.

### Controls

A bar of toggle-button groups across the top; the frames below. One global state object `S`
drives everything: a toggle sets `S[key]` and calls `render()`.

- **Global groups**: theme (light/dark), device sizes.
- **Page**: which page or screen is shown.
- **Per-page settings**: each a labeled list of options, shown only for its page.
- Label competing designs `A · …`, `B · …`, `C · …`, with a one-line "why" per page stating the
  trade-offs.
- Add a toggle for **every state of a flow**: empty, loading, error, success, dialog open, menu
  open. A button that opens nothing is a gap in the review.

### Frames

Render each page into `srcdoc` iframes at real viewport sizes, so media queries, `100dvh` and
`position: fixed` behave as on a device.

- Phones in a bezel: 390×844, 375×667, 430×932.
- Desktop 1440×900, scaled with `transform: scale(.6)`.
- An "Open full size" link per frame (blob URL).
- Never fake mobile by resizing the browser window: that gives one size at a time and screenshot
  coordinates that no longer match the viewport.

### Compare against today

Beside the mockup (`B · Redesign`), show the current product in an iframe from its local dev
server (`A · Today`) at the same sizes. Judge every change against what exists.

### Many variants at once

When the question is visual (4 share-text formats, 10 color sets), render a gallery grid of every
variant at once instead of one toggle at a time. Use realistic, contrasting sample data side by
side (e.g. a weak and a strong user, a short and a long name).

## Automated checks

Numbers catch what eyes miss; screenshots catch what numbers miss. Do both, every round.

Drive the page with browser JS (Claude in Chrome `javascript_tool` or similar). Loop over
pages × states × sizes × themes, re-render, and measure inside each iframe:

- horizontal overflow (`scrollWidth > clientWidth`);
- vertical scroll on screens meant to fit one viewport;
- dialogs off-screen or scrolling;
- positions the design promises (e.g. "X is exactly centered").

Each tool call times out (~45 s). Define helpers on `window` in one call, then run the loop in
batches. Check the console for errors. Then screenshot the failures and a sample of the rest.

```js
// Call 1: helpers. srcdoc frames are same-origin, so their documents are readable.
window.check = async (state) => {
  Object.assign(S, state); render();
  await new Promise(r => setTimeout(r, 150)); // let frames load
  return [...document.querySelectorAll('iframe[srcdoc]')].flatMap(f => {
    const d = f.contentDocument.documentElement, bad = [];
    if (d.scrollWidth > d.clientWidth) bad.push('h-overflow');
    if (d.scrollHeight > d.clientHeight) bad.push('v-scroll');
    return bad.length ? [{ ...state, w: f.width, bad }] : [];
  });
};
// Call 2..n: one batch each, e.g. one page × all states × both themes.
```

## Pitfalls

- Background tabs pause `requestAnimationFrame`: animations look frozen. Review in a foreground tab.
- Re-render after every state change, or toggles show stale pressed states.
- Translucent fills let the backdrop show through. Decide on purpose which elements are opaque.
- Mockups drift from the product. Re-seed from real tokens when the product changes.

## Round workflow

1. Collect the user's notes.
2. Update the mockup as the next `vN.html`.
3. Run the automated checks; fix and repeat until clean.
4. Screenshot-verify.
5. Record each decision, and the alternatives rejected, in the project's design record if it has
   one. Mark open questions.
6. Reply: what changed, then open questions in priority order, each with options and a
   recommendation. Decide easy calls yourself and say so.

## Teardown

When the design work ends: stop the `http.server` (confirm the port is free), and delete scratch
files the user did not ask to keep.
