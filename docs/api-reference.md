# API reference

v0.1. Signatures verified against the shipped source.

## `CircularDisplay(diameter=256, safe_inset=8)`

Geometry of a round panel. Frozen dataclass.

| member | returns | notes |
|---|---|---|
| `radius` | float | `diameter / 2` |
| `center` | (float, float) | |
| `usable_radius` | float | `radius - safe_inset` |
| `half_chord(y)` | float | half-width at scanline `y`; `0.0` outside |
| `line_width(y_top, y_bottom)` | int | usable width, constrained by the edge farther from the equator |
| `line_left(y_top, y_bottom)` | int | left x of a centred line box |
| `widest_band(line_height, n_lines)` | float | `y_top` for a vertically centred block |
| `fits(y_top, y_bottom, min_width=24)` | bool | wide enough to hold anything useful |

`HALO` is a preset: `CircularDisplay(diameter=256, safe_inset=8)`.

## `Font(path, size, line_gap=0.25)`

Raises `FontLoadError` if the face cannot be loaded — deliberately, rather than
substituting a default at the wrong size.

| member | returns | notes |
|---|---|---|
| `ascent`, `descent` | int | from the face, shared by every line |
| `line_height` | int | `(ascent + descent) * (1 + line_gap)` |
| `advance(text)` | int | width in px, includes side bearings |
| `max_feasible_lines(display, min_width=24)` | int | how many lines actually fit |
| `wrap(text, width_at, y_start, max_lines=None)` | `(lines, leftover)` | `width_at(y_top, y_bottom) -> int`; pass a constant for a rectangle |
| `layout(text, display, max_lines=5, center_block=True)` | `Layout` | `max_lines` is clamped to what fits |
| `rasterize(run, levels)` | `PIL.Image` (L) | coverage map quantized to `levels` |

`wrap`'s `width_at` callback is the shape-agnostic seam. Pass
`display.line_width` for a circle, `lambda a, b: 200` for a 200px rectangle,
anything else for a notched or D-shaped panel.

## `Layout`

| member | returns | notes |
|---|---|---|
| `runs` | `list[GlyphRun]` | |
| `leftover` | str | text that did not fit — **check this** |
| `truncated` | bool | `bool(leftover)` |

Iterable and indexable; `len()` gives the line count.

## `GlyphRun`

`text`, `x`, `baseline`, `width`. Positioned in display space.

## `Surface` (ABC)

| method | notes |
|---|---|
| `size` | `(w, h)` |
| `fill_rect(x, y, w, h, color_index)` | |
| `blit_coverage(coverage, x, y, palette_base, levels)` | writes palette indices; **not** alpha-blended |
| `present()` | flush; no double buffer exists on device |

Implementations: `PILSurface(width, height, palette)` — adds `to_rgb()`,
`dirty`, `ops`. `SpriteSurface(width, height, palette)` — accumulates
`ops: list[SpriteOp]`, unverified on hardware.

## `SpriteOp`

`width`, `height`, `num_colors`, `palette_data`, `pixel_data`, `x`, `y`.
Field names mirror `brilliant_msg.TxSprite`.

## Functions

`render_text(surface, font, text, display=HALO, max_lines=5, levels=4, palette_base=0) -> Layout`

`ramp_palette(levels, fg=(255,255,255)) -> list[int]` — flattened RGB ramp.
