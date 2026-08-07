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

## The device boundary

Everything above `surface.py` is expressed against the `Surface` ABC — three
verbs: `fill_rect`, `blit_coverage`, `present`. Three implementations keep it
honest; if a Halo-ism leaks upward, `PILSurface` diverges and the golden tests
fail.

This is deliberate. A library that renders on one vendor's panel is an
accessory to that vendor. One that renders anywhere is a standard.
