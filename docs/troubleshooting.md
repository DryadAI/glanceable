# Troubleshooting

## Nothing renders / blank output

Check `len(layout)`. In v0.1 this was a real bug: asking for more lines than
the panel could hold pushed the layout origin off-glass and returned an empty
result silently. It is fixed and pinned by
`test_never_returns_blank_for_oversized_request`, but if you see it again,
compare `font.max_feasible_lines(HALO)` against your `max_lines`.

## Text ends mid-sentence

You did not check `layout.truncated`. It is never dropped — it is in
`layout.leftover`. Either paginate, reduce the font size, or append an
ellipsis yourself.

## `FontLoadError`

Intentional. The path is wrong or the face is unreadable. The stock SDK path
silently substitutes a default bitmap font that ignores your size, which is
much harder to debug than a crash. Pass a real `.ttf` path.

## Text looks chunky / stair-stepped

You are rendering at `levels=2`. Use `levels=4`. Halo has 16 palette entries;
spending 4 on a coverage ramp is cheap and is the largest single legibility
win available.

## Halo around text on a coloured background

Known limitation. `blit_coverage` writes palette indices rather than
alpha-blending, so it is correct only over a background matching
`palette_base`. Render on black for now.

## Words break with hyphens unexpectedly

A single word wider than the chord is hyphenated rather than allowed to
overflow, because an overflowing word on a round panel disappears behind the
bezel. Reduce the font size or shorten the string.

## Non-Latin text is wrong

Expected. `advance()` is a per-string `getlength`, which is wrong for any
script needing contextual shaping. No BiDi, no CJK. Latin only in v0.1.

## It does not work on my actual glasses

It has never been run on hardware. `SpriteSurface` emits against published
`brilliant_msg` 7.0.0 shapes but the wire format is unconfirmed. If you have a
device and try it, please open an issue either way — that report is the single
most valuable contribution right now.
