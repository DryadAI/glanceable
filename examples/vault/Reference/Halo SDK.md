---
title: Halo SDK
tags: [reference, brilliant]
source: brilliant-msg 7.0.0 from PyPI
---

Established by *reading the package*, not from memory.

<div class="admonition warning">
  <script>console.log("this must never reach the glass")</script>
  Raw HTML lives in plenty of real notes.
</div>

## TxTextSpriteBlock

It has **no word wrap**. It splits on `\n` only; its `width` parameter merely
sizes the scratch buffer, and callers are given no metrics to wrap *with*.

- crops each line to its own ink bbox, so baselines drift between lines
- hard-thresholds coverage at `>127`, discarding antialiasing
- on TTF load failure falls back to `ImageFont.load_default()`, which ignores
  `font_size` entirely[^silent]

`TxPlainText` documents x as 1-640 and y as 1-400 — **Frame's** 640×400 panel.
The text path was never re-fitted to Halo.

## Sprites

Halo *is* a first-class sprite target: `sprite.lua` notes "Frame indexes are the
color names, Halo indexes are 0-15". 16-colour palettes work.

One draw is two messages:

```lua
-- device side
local sprite = data.app_data[SPRITE_MSG]
local coords = data.app_data[COORDS_MSG]
frame.display.bitmap(coords.x, coords.y, sprite.width, 2, coords.offset, sprite.pixel_data)
```

Nothing in the SDK knows the display is round. Zero occurrences of circle,
radius, or a 256 display bound.

---

See also [[Chord Solver]] and the ![[wire-format.png]] diagram.

[^silent]: This is the single worst behaviour in the stock path: the text
    renders at the wrong size rather than raising, so it looks like a layout
    bug rather than a font-loading bug.
