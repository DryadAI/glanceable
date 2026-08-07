# glanceable

A layout and typography engine for round, glanceable near-eye displays.

Developed against Brilliant Labs Halo's 256×256 circular microOLED. Nothing
above `surface.py` contains a Halo-specific call.

![stock vs glanceable](docs/comparison.png)

## Why

The Brilliant SDK ships `TxTextSpriteBlock`, which rasterizes TTF text
host-side and sends it as sprites. The primitive is the right idea and is
under-specified.

**Fair comparison caveat:** stock's contract is that the *caller* pre-wraps and
passes `\n`. The middle panel above does exactly that, and it is perfectly
usable. The honest gap is narrower than "the SDK is broken" — measured on the
sample string at 13px, `glanceable` fits the same text in 4 lines instead of 5
and uses 16% more width (223px vs 193px), because the equator chord is 238px
while the largest inscribed rectangle is only 170px.

Verified against `brilliant-msg` 7.0.0:

| | stock | glanceable |
|---|---|---|
| word wrap | none — caller must pre-wrap; `width` merely sizes the scratch buffer, and no metrics are exposed to wrap *with* | greedy wrap, hyphenates over-wide words |
| line origin | each line cropped to its own ink bbox → baselines drift | single face-derived ascent → baselines exactly `line_height` apart |
| coverage | hard threshold `>127`, 1-bit | N-level quantization (default 4 of Halo's 16 palette entries) |
| bad font path | silent `load_default()`, `font_size` ignored | raises `FontLoadError` |
| overflow | clipped | surfaced in `Layout.leftover` |
| display shape | unaware — `TxPlainText` documents x:1-640, y:1-400 (Frame's panel) | chord-aware |

Nothing in the published SDK knows the display is round. Zero occurrences of
circle, radius, or a 256 display bound.

## The circular claim

On a round panel usable line width is a function of vertical position. Every
text engine ever written wraps to a rectangle, so apps either waste the middle
third of the glass or clip against the curve.

A line box is a rectangle, so it is constrained by whichever of its two
horizontal edges sits farther from the equator — **not** by its midpoint. Using
the midpoint is the intuitive move and it clips descenders near the poles.
`test_line_width_uses_narrow_edge_not_midpoint` pins this.

## Install

```bash
pip install -e ".[dev]"
pytest -q                      # 20 passed
python examples/compare.py     # regenerates docs/comparison.png
```

## Use

```python
from glanceable import (Font, PILSurface, find_system_font,
                        ramp_palette, render_text)

surface = PILSurface(256, 256, ramp_palette(4))
layout = render_text(surface, Font(find_system_font(), 13), "…", levels=4)

if layout.truncated:
    ...  # paginate; never silently cut off
surface.to_rgb().save("frame.png")
```

Swap `PILSurface` for `SpriteSurface` to emit `TxSprite`-shaped payloads.

## Docs

- [Getting started](docs/getting-started.md)
- [Core concepts](docs/core-concepts.md) — display model, legibility rules
- [API reference](docs/api-reference.md)
- [Troubleshooting](docs/troubleshooting.md)
- [CLAUDE.md](CLAUDE.md) — constraints for contributors and AI assistants

## Status — v0.1, **never run on hardware**

Stated plainly because the point of this project is being the implementation
you can trust.

- `SpriteSurface` emits against published `brilliant_msg` 7.0.0 shapes but has
  **not** been round-tripped on a physical Halo. The wire format is unconfirmed.
- No device-side Lua counterpart yet. Next: port the dirty-flag tree from
  CitizenOneX's `base_layout.lua` and validate against the emulator's PIL
  framebuffer.
- `blit_coverage` writes palette indices rather than alpha-blending, so it is
  correct only over a background matching `palette_base`.
- Latin only. No BiDi, no shaping, no CJK.
- No glyph atlas caching; every run rasterizes fresh.

## Deliberately omitted: animation

Peripheral motion detection is pre-attentional — anything that moves out there
hijacks attention involuntarily, whether or not it matters. Animation in a
glanceable-display toolkit encourages the exact failure mode the toolkit exists
to prevent. This is a design decision, not a missing feature.

## License

MIT. Layout-tree lineage credited to CitizenOneX on adoption.
