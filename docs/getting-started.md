# Getting started

## Install

```bash
git clone https://github.com/DryadAI/glanceable
cd glanceable
pip install -e ".[dev]"
pytest -q            # expect: 20 passed
```

## Render your first frame

```python
from glanceable import Font, PILSurface, find_system_font, ramp_palette, render_text

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

## Emit for a device instead of an image

```python
from glanceable import SpriteSurface

surface = SpriteSurface(256, 256, ramp_palette(4))
render_text(surface, font, "…", levels=4)
for op in surface.ops:
    ...  # op.width, op.height, op.palette_data, op.pixel_data, op.x, op.y
```

These mirror `brilliant_msg.TxSprite` field names. **Unverified on hardware** —
see the README status section.
