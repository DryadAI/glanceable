# Getting started

## Install

```bash
git clone https://github.com/DryadAI/glanceable
cd glanceable
pip install -e ".[dev]"
pytest -q            # expect: 252 passed
```

## Render your first frame

```python
from glanceable import (HALO, Font, PILSurface, find_system_font,
                        ramp_palette, render_text)

font = Font(find_system_font(), 13)   # or pass your own .ttf path
surface = PILSurface(256, 256, ramp_palette(4))

layout = render_text(surface, font, "Rain starting in 20 minutes", levels=4)
surface.to_rgb().save("frame.png")
```

`ramp_palette(4)` builds a black→white ramp using 4 of Halo's 16 palette
entries. `levels=4` tells the rasterizer to quantize glyph coverage to those
4 steps rather than hard-thresholding to 1-bit.

## Always check for overflow

Text that does not fit is **never** dropped — it comes back to you:

```python
if layout.truncated:
    print("did not fit:", layout.leftover)
```

This is the single most important habit. A HUD that quietly cuts a sentence in
half is worse than one that paginates or shows an ellipsis.

## Ask how much will fit before you commit

```python
font.max_feasible_lines(HALO)   # how many lines this size can hold
font.advance("some text")       # width in px, including side bearings
font.line_height                # baseline-to-baseline spacing
```

`max_lines` is a ceiling, not a demand — it is clamped to what the panel can
physically hold, so asking for 6 lines at 28px gives you what fits rather than
a blank screen.

## Target a different panel

`CircularDisplay` is a value object. Nothing is hardcoded to Halo:

```python
from glanceable import CircularDisplay
watch = CircularDisplay(diameter=390, safe_inset=12)
render_text(surface, font, "…", display=watch)
```

## Render a markdown note

Needs the optional extra: `pip install "glanceable[markdown]"`.

```python
from glanceable import HALO, Font, PILSurface, find_system_font, ramp_palette
from glanceable.markdown import render_markdown

surface = PILSurface(256, 256, ramp_palette(4))
page = render_markdown(surface, note_source, font, HALO, page=0, levels=4)

while page.has_more:                 # driven by YOU — a click, a key, a gesture
    page = render_markdown(surface, note_source, font, HALO, page=page.page + 1)
```

`page` is an index, not a cursor: the same call with the same arguments always
gives the same page, and you can ask for them out of order. There is no
auto-advance and no scrolling — see the legibility rules in
[core concepts](core-concepts.md).

Check all three places content can be before assuming something was lost:

```python
page.leftover_source        # did not fit yet
page.metadata.dropped       # deliberately degraded — images, embeds, HTML
page.metadata.unrenderable  # the face has no glyph for these
page.metadata.wikilinks     # [[Target]] kept for you to act on
```

## Emit for a device instead of an image

```python
from dataclasses import asdict
from glanceable import SpriteSurface

surface = SpriteSurface(256, 256, ramp_palette(4))
render_text(surface, font, "…", levels=4)

for payload, coords in surface.messages():
    ...  # TxSprite(**asdict(payload)), then TxSpriteCoords(**asdict(coords))
```

One draw is **two** messages, not one: `TxSprite` carries pixels and has no
position, and `TxSpriteCoords` positions it by `code`. Send the payload before
the coords. `SpritePayload` and `SpriteCoords` mirror those two SDK dataclasses
field for field, so `asdict()` needs no translation step.

`surface.ops` gives the same thing as `SpriteOp` objects, which expose `.x`,
`.y`, `.width`, `.height` and `.code` as passthroughs; the pixel fields live on
`op.payload`. **Unverified on hardware** — see the README status section.
