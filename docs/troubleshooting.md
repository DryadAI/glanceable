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

Moving the ramp with `palette_base` is not the workaround: `SpriteSurface`
raises on a non-zero base, because `TxSprite.pack()` masks every index to the
declared bit depth and so sends identical bytes whatever the base. Keep the ink
ramp at the bottom of the palette.

## Words break with hyphens unexpectedly

A single word wider than the chord is hyphenated rather than allowed to
overflow, because an overflowing word on a round panel disappears behind the
bezel. Reduce the font size or shorten the string.

## Non-Latin text is wrong

Expected. `advance()` is a per-string `getlength`, which is wrong for any
script needing contextual shaping. No BiDi, no shaping.

CJK through `glanceable.markdown` is **conserved but broken on the wrong
boundaries**: line filling splits on whitespace, so a spaceless run is treated
as one long word and hyphen-broken. No characters are lost — the corpus test
pins that — but the break points are meaningless for the script. Dictionary
breaking is a roadmap item, not a bug report.

## CJK renders as empty boxes

The face has no CJK glyphs. DejaVu Sans — which `find_system_font()` usually
picks — has none, so every character comes out as `.notdef` tofu. This is not
silent: check `metadata.unrenderable`, which lists every character the face
could not draw.

```bash
python examples/obsidian_bridge.py --query 日本語
#   !! page 0: face cannot draw 、 。 い が く こ … 円 形 応 性
```

Point `GLANCEABLE_FONT` at a CJK-capable face (Noto Sans CJK, Source Han Sans)
and the tofu goes away — the *line breaking* will still be wrong, which is the
separate limitation above.

## `MarkdownDependencyError`

Intentional, and the message tells you the fix: `pip install
"glanceable[markdown]"`. Core depends only on Pillow; the markdown layer needs a
CommonMark parser, so it is an optional extra imported lazily. `glanceable`
itself still imports fine without it — that is why `glanceable.markdown` is not
re-exported from `__init__.py`.

## Markdown text disappeared

It did not. Check all three destinations before filing a bug:

```python
page.leftover_source          # did not fit yet — request the next page
page.metadata.dropped         # images, embeds, opaque fences, HTML, footnote refs
page.metadata.unrenderable    # the face has no glyph for these characters
```

`unrenderable` is the one people miss. PIL draws a character the face does not
cover as `.notdef` — frequently invisible — and raises nothing. Emoji in a
monochrome face are the usual cause.

## My frontmatter rendered as a heading

Not through `glanceable.markdown`, which strips it first. If you see this, you
are feeding source to a CommonMark parser directly: `---\ntitle: X\n---` is a
thematic break followed by a *setext H2*, so `title: X` becomes a heading. Use
`parse_markdown`, and read `metadata.frontmatter_raw`.

Note that `metadata.frontmatter` is a flat `key: value` scan, **not** a YAML
parse — `tags: [a, b]` arrives as the literal six-character string. Parse
`frontmatter_raw` yourself if you need real YAML; this package will not pull in
a YAML dependency for it.

## A table turned into a list of `key: value` lines

Working as intended. `key: value` is lossless only at two columns; at three or
more it silently discards the rest. Records keep every cell and degenerate to
exactly `key: value` when there are two columns. If you would rather lose the
table than the lines, `Policy(table="omit")` states the omission and records the
shape in metadata.

A cell that vanishes entirely is a different thing: GFM truncates a row with
more cells than headers *inside the parser*, before this library sees a token.
Those are counted from the source and reported as `Dropped(kind="table-cell")`.

## Code lines end with `↳`

That is a continuation marker, not corruption. A code line too wide for the
chord is broken rather than reflowed, clipped, or pushed into `leftover` —
pushing it to leftover would make the tail reappear *after* the lines that
followed it, which is wrong order rather than merely incomplete. Set
`Policy(code_continuation=("↳", "\\"))` to change it.

## `TypeError: TxSprite.__init__() got an unexpected keyword argument 'x'`

You splatted a whole op into `TxSprite`. One draw is *two* messages, not one:
`TxSprite` carries pixels and has no position, and `TxSpriteCoords` positions
it by `code`. Use the pair:

```python
from dataclasses import asdict
for payload, coords in surface.messages():
    tx = TxSprite(**asdict(payload))
    tc = TxSpriteCoords(**asdict(coords))
```

`SpritePayload` and `SpriteCoords` mirror those two SDK dataclasses field for
field, so `asdict()` needs no translation step. Send the payload before the
coords that position it.

## Cannot install `brilliant-msg`: `ResolutionImpossible`

```
brilliant-ble 3.1.1 depends on bleak<1.0.0 and >=0.22.3
```

`bleak` below 1.0 has no wheels for Python 3.13+. Build the device toolchain on
3.10–3.12; that is also what CI tests. glanceable itself is unaffected — it
depends only on Pillow and runs anywhere ≥3.10.

Keep the SDK out of the environment you run `pytest` in. If `brilliant_msg` is
importable during tests, a device-specific call can leak above `surface.py` and
the golden tests will not catch it, which is precisely what hard rule 1 exists
to prevent. A separate venv for device work costs nothing:

```
uv venv --python 3.12 ~/.venvs/halo-dev
uv pip install --python ~/.venvs/halo-dev/bin/python brilliant-msg==7.0.0
```

## No Halo found when connecting

`BrilliantBle.connect()` takes the first Halo/Frame it discovers, so if nothing
is advertising it simply times out. Confirm the glasses are on and unpaired
from any phone app holding the BLE link — the device accepts one central at a
time. `bluetoothctl devices` will not list it unless it is bonded; a live scan
is the real check.

## Tests pass locally but fail on a fresh machine or runner

Font availability. `find_system_font()` searches the usual system paths and
there is no bundled face. Install one and point at it explicitly:

```
apt-get install -y fonts-dejavu-core
export GLANCEABLE_FONT=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf
```

This is what the CI workflow does, and pinning one face is also how golden
comparisons stay stable across distros.

Neither failure is silent: `find_system_font()` raises `FileNotFoundError`
listing every path it searched, and `Font` raises `FontLoadError` if the face
itself will not load.

## It does not work on my actual glasses

It has never been run on hardware. That is ROADMAP item 2, under "Prove the
bet" — second only to getting a non-Brilliant backend running, because the
device-agnostic boundary is the claim that most needs testing.

What *is* checked: the emitted payloads were validated against the real
`brilliant_msg` 7.0.0 classes. Field names match both SDK dataclasses exactly,
every op constructs and packs, sprites come out at `bpp=2`, and palette indices
stay inside Halo's documented 0–15. That found and fixed one genuine defect,
the sprite/coords split above.

What is still unconfirmed, and cannot be settled by reading the SDK:

- **Origin indexing.** `x`/`y` are emitted 0-based, matching this library's
  geometry. The SDK documents `1..640` — Frame's panel, the same stale bound
  `TxPlainText` carries. If everything lands one pixel off, this is why.
- Whether the device accepts the sprite/coords ordering as sent.
- Whether `code` allocation collides with anything the firmware reserves.

If you have a device and try it, please open an issue either way — that report
is the single most valuable contribution right now.
