---
title: Chord Solver
tags: [halo, geometry, active]
status: in-progress
aliases:
  - chords
  - the geometry note
---

# Chord Solver

On a round panel usable line width is a *function of vertical position*. Every
text engine ever written wraps to a rectangle, so apps either waste the middle
third of the glass or clip against the curve.

## Line budget

```python
def half_chord(self, y: float) -> float:
    """Half-width of the usable circle at scanline `y`. 0.0 outside."""
    dy = abs(y - self.radius)
    if dy >= self.usable_radius:
        return 0.0
    return math.sqrt(self.usable_radius ** 2 - dy ** 2)
```

The scale of the win, measured at 13px on the sample string: 4 lines instead of
5, 223px vs 193px of width. Worth roughly a third of the glass — real, but not
"the SDK is broken".

> [!NOTE] Fair comparison
> Stock's contract is that the *caller* pre-wraps and passes `\n`. Given that
> contract it is perfectly usable. The honest gap is narrower than it looks.
>
> > [!TIP] Corollary
> > Do not lead with the comparison. Lead with the geometry.

## Open

1. Confirm the wire format on a physical Halo
2. Port the dirty-flag tree from `base_layout.lua`
3. Glyph atlas caching — see https://github.com/DryadAI/glanceable/blob/main/ROADMAP.md#build-on-top--once-the-layer-is-trusted for the ordering

Related: [[Halo SDK]], [[Pathological]], and an unresolved link to
[[Saccade Budget]] that has no note yet.
