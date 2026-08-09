# Core concepts

## The panel is a circle, and that is the whole problem

Halo's display is 256×256 pixels — but round. Essentially every text layout
engine ever written assumes a rectangle.

Two ways to get this wrong:

- **Wrap to the inscribed rectangle.** Safe, but the largest rectangle fitting
  inside the usable circle is only 170px wide, while the widest line across the
  middle is 238px. You throw away about a third of the glass.
- **Wrap to the bounding box.** Uses the full 256px, and clips against the
  curve near the top and bottom.

## Chords

The width of a circle at a given height is a *chord*. It is widest at the
equator and narrows toward the poles. `CircularDisplay.half_chord(y)` solves
it; `line_width(y_top, y_bottom)` gives the usable width for a line box.

The subtle part, and the reason this library exists:

> A line of text is a rectangle with a top and a bottom edge. It is limited by
> whichever edge is **closer to the rim** — not by its midpoint.

Using the midpoint overestimates the available width for any line not centred
on the equator, and the overhang clips the descenders of letters like g, y, p.

## Blocks are centred on the equator

Because chord width peaks at the centre, a block of text pinned to the top
both wastes width and reads worse. `layout()` centres the block vertically.

Re-centring is not a simple loop: centring for N lines can itself produce N±1
lines, and that can oscillate (5→6→5) rather than converging. `layout()`
searches for a line count that is *self-consistent* — one where wrapping at
the y that centres N lines actually produces N lines.

## Baselines, not bounding boxes

Metrics come from the font face once (`ascent`, `descent`), so every line
shares a baseline and lines sit exactly `line_height` apart regardless of
whether they contain ascenders or descenders. Cropping each line to its own
ink bbox — what the stock SDK path does — makes text visibly bounce.

## Coverage, not 1-bit

Antialiased coverage is quantized to N levels rather than thresholded. At
12–14px on a high-DPI panel, aliased stems are the single largest legibility
cost, and Halo supports 16 palette entries. Four is a good default: it costs
4 entries and buys back most of the stem definition.

## Legibility rules

Written down because they are easy to get wrong:

- **Do not animate.** Peripheral motion detection is pre-attentional; anything
  that moves out there hijacks attention involuntarily. This is why the
  library ships no animation support.
- **Centre on the equator.** Widest chord and the easiest saccade target.
- **Prefer 4-level coverage over 1-bit.**
- **Respect the safe inset.** The outermost ring is where lens vignetting and
  eye-box misalignment bite; glyphs there are unreliable even though the
  pixels are addressable.
- **Fewer words.** The constraint is the wearer's attention, not the panel.

## Markdown degradation

Markdown assumes a wide rectangular viewport and rich typography. A 256px circle
at 13px gives ~33 characters at the equator and ~9 on the outermost usable line,
across roughly five to seven lines. Most syntax must degrade rather than render.

The governing rule is that every piece of source reaches exactly one of three
places — **the glass, `leftover_source`, or `metadata`.** There is no fourth.

| element | treatment | why |
|---|---|---|
| frontmatter | stripped **before** the parser sees it; exposed as raw text plus a flat non-YAML scan | CommonMark reads a leading `---` block as a thematic break plus a setext H2, so raw source renders frontmatter as a heading |
| headings | one emphasis tier: an optional `emphasis_font`, else a prefix glyph; level kept in metadata | there is no room for six, and `Font` has no style axis |
| bold / italic / strike | markup dropped, text kept | no bold face exists to collapse *to*, so nothing renderable is lost |
| inline code | backticks stripped, text kept | |
| fenced code | never reflowed, never joined; over-wide lines broken at the chord with a visible continuation marker, in a rectangular sub-viewport | pushing the tail to `leftover` would make it reappear *after* the following lines — wrong order is worse than incomplete. Per-line chords would give a ragged left edge |
| opaque fences (`dataview`, `mermaid`, …) | dropped, full body in metadata | they are programs, not prose |
| tables | one `header: cell` line per column per row | `key: value` is lossless only at two columns and silently discards the third onward. Records degenerate to `key: value` at two columns and lose nothing at four. `omit` is available, never the default |
| callouts | `[!TYPE] Title` collapses to a prefixed lead line; body follows as its own block | |
| lists | depth becomes indent, capped not dropped; hanging-indent continuations | three levels already costs a tenth of the equator chord |
| task items | `[ ]` / `[x]`, ASCII by default | a fancier glyph the face lacks is drawn as an invisible `.notdef` and raises nothing |
| wikilinks | display text rendered, target retained in metadata | the only vault-flavoured construct allowed in |
| links | link text rendered; bare URLs over 32 chars elided to host + ellipsis, full target in metadata | an unelided 200-char URL is one unbreakable token that eats the whole display |
| images / embeds | dropped; alt text **and** target in metadata | the alt text is something the author wrote |
| footnotes | marker dropped; definition body in metadata | definitions are real prose, not syntax |
| HTML blocks | opaque, dropped, content in metadata | stripping tags would happily render the body of a `<script>` |

Pagination is a discrete index and a pure function of its inputs. Requesting
page 3 re-flows pages 0–2 to find where it starts — deterministic, cheap on
note-sized input, and the honest price of having no hidden state to desync.

There is no scroll, no fade, no auto-advance. See the legibility rules above:
that is rule 2, not an unfinished feature.

## The device boundary

Everything above `surface.py` is expressed against the `Surface` ABC — three
verbs: `fill_rect`, `blit_coverage`, `present`. Three implementations keep it
honest; if a Halo-ism leaks upward, `PILSurface` diverges and the golden tests
fail.

This is deliberate. A library that renders on one vendor's panel is an
accessory to that vendor. One that renders anywhere is a standard.
