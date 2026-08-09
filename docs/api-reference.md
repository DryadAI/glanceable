# API reference

v0.2. Signatures verified against the shipped source.

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

## `SpritePayload` / `SpriteCoords` / `SpriteOp`

One draw is **two** messages on the wire. `brilliant_msg` 7.0.0 splits pixels
from placement, so a single flat struct is wrong — splatting it into `TxSprite`
raises `TypeError` on `x`.

| type | fields | mirrors |
|---|---|---|
| `SpritePayload` | `width`, `height`, `num_colors`, `palette_data`, `pixel_data`, `compress=False` | `TxSprite` — carries no position |
| `SpriteCoords` | `code`, `x`, `y`, `offset=0` | `TxSpriteCoords` — `code` binds it to its payload |
| `SpriteOp` | `payload`, `coords` | one accumulated draw |

`SpriteOp` exposes `.x`, `.y`, `.width`, `.height` and `.code` as passthroughs so
op logs stay comparable against `PILSurface`'s `(x, y, w, h)` tuples. The pixel
fields are on `.payload`, not on the op.

`SpriteSurface.messages() -> list[tuple[SpritePayload, SpriteCoords]]` gives the
frame in draw order. Send the payload before the coords that position it.

## `glanceable.markdown`

Needs the optional extra: `pip install "glanceable[markdown]"`. Raises
`MarkdownDependencyError` if the parser is absent. Not re-exported from
`glanceable` — import from `glanceable.markdown`.

| function | returns | notes |
|---|---|---|
| `parse_markdown(source, policy=Policy())` | `MarkdownDoc` | pure; no font, no display |
| `layout_markdown(source_or_doc, display, font, *, page=0, max_lines=None, emphasis_font=None, policy=Policy())` | `MarkdownLayout` | pure; `page` is an index, not a cursor |
| `render_markdown(surface, source, font, display=None, *, page=0, ..., levels=4, palette_base=0)` | `MarkdownLayout` | lays out and draws |
| `usable_lines(font, display, policy=Policy())` | int | stricter than `Font.max_feasible_lines` |
| `has_glyph(font, ch)` | bool | whether the face can actually draw it |

`MarkdownDoc`: `blocks`, `metadata`, `source`, `source_lines`. Immutable, and
independent of any font — one parse can be laid out against several panels.

`MarkdownLayout`:

| member | returns | notes |
|---|---|---|
| `lines` | `tuple[MarkdownLine, ...]` | `run`, `block`, `kind`, `level`, `font` |
| `runs` | `tuple[GlyphRun, ...]` | base-font view; `Layout`-compatible |
| `leftover_source` / `leftover` | str | continuation source — **check this** |
| `truncated` / `has_more` | bool | |
| `metadata` | `Metadata` | |
| `page` | int | |
| `text()` | str | rendered text, one line per line |

Iterable and indexable like `Layout`, so `render.render_text`'s blit loop works
on it unchanged.

`Metadata`: `frontmatter_raw`, `frontmatter`, `wikilinks`, `links`, `footnotes`,
`dropped`, `reformatted`, `unrenderable`. Every field is document-scoped except
`unrenderable`, which is page-scoped — it cannot be known before a face is
chosen. `frontmatter` is a flat `key: value` scan, **not** a YAML parse.

`Policy` — frozen dataclass holding every degradation knob: `table`
(`"records"` | `"omit"`), `max_list_depth`, `indent_px`, `min_line_width`,
`url_elide_over`, `opaque_fences`, `hang_max_px`, `rule_fraction`, and the
marker glyphs. Each marker is a `(preferred, ascii_fallback)` pair; the
preferred form is used only if the loaded face has the glyph.

`emphasis_font` must not have a taller `line_height` than `font` — the page
shares one baseline grid — and raises `ValueError` if it does.

## Functions

`render_text(surface, font, text, display=HALO, max_lines=5, levels=4, palette_base=0) -> Layout`

`ramp_palette(levels, fg=(255,255,255)) -> list[int]` — flattened RGB ramp.
