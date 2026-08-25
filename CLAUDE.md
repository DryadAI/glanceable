# CLAUDE.md

Context for any AI assistant or new contributor working on this repo. Read
this before writing code. It exists because a parallel brainstorming session,
lacking this context, produced 800 lines of unverified widgets under a
different name with an animation framework that contradicts the core design
principle. Constraints belong in the repo, not in one conversation's memory.

It only works if it is read. A later session reviewed `SpriteSurface`, concluded
Halo could not receive sprites at all, and proposed deleting it — contradicting
a finding recorded in this file three sections down. Two backends were written
against the wrong premise before anyone opened this. Read it first.

## What this is

A layout and typography engine for round, glanceable near-eye displays.
Developed against Brilliant Labs Halo (256×256 circular microOLED), but
explicitly not locked to it.

It is **not** a widget library yet. It is the layer widgets will be built on.
Do not add widgets until the text layer is validated on hardware.

Module map, bottom to top:

| module | depends on | notes |
|---|---|---|
| `geometry.py` | — | chord solver |
| `surface.py` | Pillow | the device boundary; see rule 1 |
| `damage.py` | — | rectangles and frame diffing; device-free |
| `retained.py` | damage, surface | damage repaint over any backend |
| `typography.py` | geometry | metrics, chord-aware wrap, rasterization |
| `fonts.py` | — | cross-platform face discovery |
| `render.py` | all of the above | `render_text` convenience |
| `markdown.py` | typography, geometry, surface | markdown → circular display |

`damage.py` is named apart from `geometry.py` deliberately: one is the shape of
the glass, the other is what changed since the last frame. `retained.py` wraps a
`Surface` and is itself a `Surface`, so it contains no device call and sits
above the boundary without breaking rule 1.

`markdown.py` is a *renderer*, not a widget: it turns document structure into
`GlyphRun`s on the same grid everything else uses. It is the only module with an
optional dependency, and it is deliberately not re-exported from
`__init__.py` — importing it eagerly would turn a missing extra into an
`ImportError` on `import glanceable`.

## Hard rules

1. **Nothing above `surface.py` may contain a device-specific call.** All
   drawing goes through the `Surface` ABC. Three backends keep this honest: if
   a Halo-ism leaks upward, `PILSurface` stops matching and the golden tests
   fail. A library that renders on one vendor's panel is an accessory; one
   that renders anywhere is a standard. This rule is the entire strategic bet.

2. **Do not add animation.** Peripheral motion detection is pre-attentional —
   anything that moves out there hijacks attention involuntarily, whether or
   not it matters. An animation framework in a glanceable-display toolkit
   encourages the exact failure mode the toolkit exists to prevent. This is a
   deliberate omission, not a gap.

3. **Never claim verification that has not happened.** No "production-ready"
   on unrun code. No CI badge over tests that do not execute. The entire
   positioning of this project is being the trustworthy implementation; one
   inflated claim spotted by a reviewer costs more than the feature gained.

4. **Never silently drop or truncate text.** Anything that does not fit
   surfaces in `Layout.leftover`. A HUD that quietly cuts off half a sentence
   is worse than one that shows an ellipsis.

5. **Fail loudly on bad input.** `Font` raises `FontLoadError` rather than
   substituting a default face at the wrong size, which is what the stock SDK
   path does. `markdown.py` raises `MarkdownDependencyError` rather than
   degrading to a worse parser, and rejects an `emphasis_font` taller than the
   body face rather than letting it overrun its grid slot.

6. **No new runtime dependencies without asking.** Core is Pillow-only and stays
   that way. `markdown.py` needs a CommonMark parser, so it lives behind the
   optional `glanceable[markdown]` extra and imports it lazily inside the
   function that needs it. If you add a dependency, it goes in an extra and it
   gets argued for first.

7. **Silent loss has more than one shape.** Rule 4 is about more than
   truncation. A character the loaded face does not cover is drawn by PIL as
   `.notdef` — often invisible — and raises nothing; `markdown.py` reports those
   in `Metadata.unrenderable` and picks marker glyphs only after checking
   coverage. Anything deliberately degraded is named in metadata. The three
   permitted destinations for source content are: the glass, `leftover_source`,
   or `metadata`. There is no fourth.

## Verified facts about the Brilliant SDK

Established by reading `brilliant-msg` 7.1.1 from source, not from memory.
7.1.0 was explicitly a "True-up against Halo firmware 0.8.8" — the SDK is
being tracked against the same firmware revision this project reads.

- `TxTextSpriteBlock` rasterizes TTF host-side via PIL and ships sprites. The
  primitive is sound; the typography is not.
- It has **no word wrap**. It splits on `\n` only; its `width` parameter
  merely sizes the scratch buffer. Callers must pre-wrap, and are given no
  metrics to wrap with.
- It crops each line to its own ink bbox, so baselines drift between lines.
- It hard-thresholds coverage at `>127`, discarding antialiasing.
- On TTF load failure it silently falls back to `ImageFont.load_default()`,
  which ignores `font_size`.
- `TxPlainText` documents x as 1-640 and y as 1-400 — **Frame's** 640×400
  panel. The text path was never re-fitted to Halo.
- Nothing in the SDK knows the display is round. Zero occurrences of circle,
  radius, or a 256 display bound.
- Halo *is* a first-class sprite target: `sprite.lua` notes "Frame indexes are
  the color names, Halo indexes are 0-15". 16-colour palettes work. Its
  `set_palette()` branches on `frame.HARDWARE_VERSION` and renders through
  `frame.display.bitmap`. Sprites were never a firmware primitive on *either*
  device — they are device-side Lua the SDK ships. Grepping `halo-firmware` for
  "sprite" returns nothing, and that fact proves nothing about Halo support.
- The wire format changed at 6.0.0: a `compressed` flag byte was inserted at
  header offset 5, shifting `bpp` to 6 and `num_colors` to 7. `TxSprite.pack()`
  emits `>HHBBB` = width, height, compress, bpp, num_colors, and `sprite.lua`
  parses those positions. Frame code written against a pre-6.0.0 header will
  desynchronise; the field is already carried on `SpritePayload`.
- `bpp` is derived inside `pack()` from `num_colors`, not supplied. Pixels go
  in one byte per index; `_pack_1bit`/`_pack_2bit`/`_pack_4bit` do the packing.
  Pre-packing double-encodes.
- `msg_code` is applied by `BrilliantMsg.send_message()` at send time and is
  correctly absent from both message dataclasses.
- `sprite.lua` slices the palette as exactly `num_colors * 3` bytes and takes
  everything after it as pixel data. Palette length is load-bearing.

## Verified facts about Halo firmware (0.8.8)

Read from `modules/halo/src/lua_display.c` and `applications/halo/PROTOCOL.md`.

- `frame.display.show()` is a **registered no-op**, kept for Frame
  compatibility. There is no double buffer — the canvas binds directly to the
  CDC200 layer framebuffer, so draws land in the buffer being scanned out. A
  clear-and-repaint is a full-field luminance transient, which is rule 2's
  failure mode arriving through the back door. This is documented on
  docs.brilliant.xyz; it is not a gap.
- `display.clear()` writes 196KB into live scanout. Once at startup, never per
  frame.
- All display primitives are **1-based** and subtract 1 internally.
  `text`/`rect`/`line`/`char`/`bitmap` clamp inputs below 1 up to 1 *before*
  subtracting, so an off-screen origin is shifted rather than cropped.
  `circle` and `polygon` do not clamp and handle negatives correctly.
- `display.bitmap(x, y, width, color_format, palette_offset, data, [opts])`.
  `color_format` is the colour count: 2 → 1bpp, 4 → 2bpp, 16 → 4bpp, 0 →
  RGB888 direct. **Source index 0 is always transparent regardless of offset**,
  which is exactly what `PILSurface.blit_coverage`'s mask does — both are
  indexed-with-transparent-zero.
- `palette_offset` shifts linearly and never wraps; an index pushed past 15 is
  skipped.
- Display fonts are `Dogica8px` and `DogicaBold8px` only, stored at 8px and
  integer-scaled; `set_font` requires a multiple of 8. These are the *device
  text primitive's* fonts and are irrelevant to this library, which rasterizes
  TTF host-side and ships pixels. Do not import their metrics.
- `frame.display.char()` is documented as taking a Unicode codepoint, with
  `char(0x2665)` — a heart — as the example. Only the two Dogica faces are
  registered. If those are ASCII-only that example cannot render. Reported to
  Brilliant Labs.
- Binary transfer is `frame.bluetooth.receive_callback` / `max_length()` /
  `send()` over the data channel (marker `0x01`). MTU is 512; `max_length()`
  returns MTU−1. Lua string escaping costs 4 chars/byte, so pixel data over the
  REPL would need roughly 3× the writes — it belongs on the data channel.

## The core geometric claim

On a round panel, usable line width is a function of vertical position. A line
box is a rectangle, so it is constrained by whichever of its two horizontal
edges sits **farther from the equator** — not by its midpoint. Using the
midpoint is the intuitive move and it clips descenders near the poles.
Pinned by `test_line_width_uses_narrow_edge_not_midpoint`.

Scale of the win, measured at 13px on the sample string: 4 lines instead of 5,
223px vs 193px of width. The equator chord is 238px; the largest inscribed
rectangle is 170px. Worth roughly a third of the glass — real, but not
"the SDK is broken."

## Bugs already found and fixed — do not reintroduce

Each has a named regression test. If you touch `typography.py`, run them.

- **Silent blank screen.** `line_height × max_lines` exceeding the panel
  pushed the probe origin off-glass, where every chord is zero width, and
  `layout` returned `[]` with no error. Now clamped by `max_feasible_lines()`.
- **Text silently dropped.** When two glyphs plus a hyphen exceeded the chord,
  `cut` fell to 1 and the word's remainder was discarded. Now re-queued.
- **Non-terminating re-centring.** Centring for N lines could yield N±1 and
  oscillate (5→6→5). Iterating to a fixed point does not converge; replaced
  with a deterministic search for a self-consistent line count.
- **A test that could not fail.** The surface-agreement test compared
  `SpriteSurface` against a recomputation that ignored the PIL surface
  entirely. Both op logs are now compared directly.

### In `surface.py` (sprite wire format)

Found by diffing against `brilliant_msg` 7.1.1 source. None of these can fail
host-side — `PILSurface` never reads `palette_data` — so the suite stays green
while the glass shows garbage. They are pinned in `tests/test_retained.py`.

- **Palette length desynchronised the device parser.** The full palette was
  sent regardless of `num_colors`. `sprite.lua` reads `num_colors * 3` bytes
  and treats the remainder as pixels, so any mismatch shifts every pixel in the
  frame. `ramp_palette(4)` happens to be exactly 12 bytes, which is the only
  reason this was not already visible. It would present as a wire-format
  problem, not a palette-length one.
- **Sprite codes collided after 224 draws.** `_next_code()` derived from
  `len(self.ops)`, and `present()` never clears the log, so codes ran past
  `0xFF` and wrapped onto sprites still live on the device. Now cycles within
  `base_code..0xFF`, with `reset_codes()` for a cleared display.
- **`num_colors` could be a value the packer cannot express.**
  `max(2, len(palette) // 3)` yields e.g. 5, which `pack()` encodes as 4bpp
  while declaring 5. Now rounded to {2, 4, 16}, rejected above 16.
- **Nothing ever erased.** `blit_coverage` writes ink through a mask, so a
  re-rendered shorter line left the previous tail on the glass. Neither backend
  recovered: `SpriteSurface.present()` is a no-op and `PILSurface.present()`
  only clears `dirty`. Fixed by `RetainedSurface`, which is device-free and
  wraps either backend.
- **Sprite coordinates were emitted 0-based.** Every Halo display primitive
  does `if (v < 1) v = 1; v -= 1;`, so a 0-based origin lands every sprite one
  pixel up and left — and clamps rather than shifts anything on the top or left
  edge. `_emit` now sends `x + 1, y + 1`. The conversion lives at the wire; the
  library's geometry stays 0-based. Found by round-tripping the bytes through
  `brilliant_msg` 7.1.1 and halo-emulator, not by the host suite, which cannot
  see it.
- **`palette_base` was silently inert on the wire.** `SpriteSurface` added it
  to each pixel index; `TxSprite.pack()` then masks each index to the declared
  bit depth, so at `levels=4` (2bpp) base 4 sends 7 and base 12 sends 15 and
  both arrive as 3 — *every* base produced byte-identical output while
  `PILSurface` honoured it. The backends diverged with the suite green. Now
  `SpriteSurface.blit_coverage` raises `ValueError` on a non-zero base. The
  device mechanism is `bitmap()`'s `palette_offset`, but `sprite.lua`'s
  `set_palette()` always assigns firmware entries from index 0, so an offset
  alone points at unwritten slots; supporting it means changing the device-side
  Lua, not this method.

### In `markdown.py` (v0.2)

Each has a named regression test, and each was verified to **fail** with its fix
reverted. A test that passes either way is worse than no test; check the
discrimination, do not assume it.

- **Frontmatter rendered as a heading.** CommonMark has no concept of
  frontmatter: it reads a leading `---` block as a thematic break followed by a
  *setext H2*, so `title: Notes` reaches the glass as a heading. Frontmatter is
  stripped before the parser sees the source. The lines are blanked rather than
  deleted so every `token.map` still indexes the original file.
- **An unterminated `---` eaten to EOF.** It is a thematic break, not an
  unclosed frontmatter fence. Treating it as frontmatter swallows the note.
- **Consecutive footnote definitions collapsed into one.** `[^a]: x` and
  `[^b]: y` on adjacent lines are a *single* CommonMark paragraph joined by a
  softbreak, so a DOTALL match swallowed every definition after the first into
  the first one's body. Definitions are split line-wise, and matched on raw
  content because inline scrubbing removes the `[^a]` marker first.
- **A block duplicated or skipped at a page boundary.** `_Page.next_block`
  conflated "first block not yet started" with "the block that split". The two
  are tracked separately.
- **Code lost across a page break.** The code path counted rendered fragments
  rather than source characters, so a line broken mid-way at a page boundary
  lost the straddling piece. `_break_verbatim` now returns `(display, raw)`
  pairs whose raw halves concatenate back to the source.
- **Excess GFM table cells vanishing.** A row with more cells than headers is
  truncated *inside the parser*, before we see a token. It cannot be rendered,
  so it is counted in the source and named in metadata.
- **Metadata truncated to 60 characters.** An opaque `dataview` block whose
  metadata note stopped at 60 chars had silently lost the rest. `Dropped.detail`
  is complete, not a preview.
- **A test that could not fail, again.** The hanging-indent regression test
  stopped discriminating once callouts began splitting into lead line plus body,
  because that fixture no longer produced a long-prefix continuation. Repointed
  at a callout title long enough to wrap.
- **A fixture that tested nothing.** The composite fixture concatenated sections
  without blank lines, so a table butted against the list above it and GFM never
  saw a table at all — it became paragraph text full of pipes, and every sweep
  test that thought it covered the table path covered nothing. Found by looking
  at a rendered contact sheet, not by a test. Render and *look* at the output.
- **A split list item lost its marker**, and `leftover_source` therefore did not
  round-trip: the remainder dropped its prefix, and `_resynth` reused the
  *rendered* marker (`"• "`), which re-parses as a paragraph rather than a list
  item. Remainders keep their prefix — on a HUD there is no scrollback, so a
  continued item repeats its bullet and each page stands alone — and `_resynth`
  maps back to real markdown markers. Callout bodies carry the quote marker for
  the same reason: there is no markdown for "blockquote continuation with no
  marker", so a bare body returned as a centred paragraph.

  **Found by `examples/vault/`, not by `tests/fixtures.py`.** Invented fixtures
  only contain the mess someone thought to invent; none of them happened to
  split a list item across a page. Corpora of real-shaped input earn their keep.

## Honest status

- **Never run on hardware.** Field shapes are verified field-for-field against
  `brilliant_msg` 7.1.1 — `SpritePayload` against `TxSprite`, `SpriteCoords`
  against `TxSpriteCoords`, both in declaration order — so `asdict()` splats
  cleanly. The **x/y origin** is settled as far as host tooling can settle it:
  coordinates go out 1-based, matching `frame.display.bitmap`, verified by
  round-tripping through `brilliant_msg` 7.1.1 and halo-emulator. An emulator
  is not glass — this still wants a device before anyone calls it confirmed.
- `RetainedSurface` is host-verified against both backends. Whether a
  damaged-region update is imperceptible on real glass is a hardware question.
- No device-side Lua counterpart yet.
- `blit_coverage` writes palette indices rather than alpha-blending, so it is
  correct only over a background matching `palette_base`. On `SpriteSurface` a
  non-zero `palette_base` raises: the wire format cannot carry it.
- Latin only. `advance()` is a per-string `getlength`, wrong for any script
  needing contextual shaping. No BiDi.
- No glyph atlas caching; every run rasterizes fresh.

`markdown.py` specifically — host-side tested (215 of the suite's markdown tests
cover it: 187 unit plus 28 over the vault corpus, on 3.10, 3.12 and 3.14), never
seen by a device:

- **CJK is conserved but broken wrong.** Line filling splits on whitespace, so a
  spaceless run is one long "word" and gets hyphen-broken. No text is lost and
  the limitation is documented, but the break points are wrong for the script.
- **Left-aligned blocks have a ragged left edge near the poles**, because lists,
  tables and quotes use each line's own chord. Code blocks do not — they get a
  rectangular sub-viewport. Whether the ragged edge is acceptable is a hardware
  question and there is no hardware.
- **No widow control.** A single list item or a heading can strand alone at a
  page boundary.
- `Metadata.frontmatter` is a flat `key: value` scan, **not** a YAML parse;
  `tags: [a, b]` arrives as the literal string. `frontmatter_raw` is verbatim,
  for callers that want real YAML.
- `Metadata.unrenderable` is page-scoped; every other metadata field is
  document-scoped.
- `leftover_source` is a true source slice for whole unreached blocks, but a
  *re-synthesis* for a block split part-way, because a half-consumed paragraph
  has no source range. Round-trip stability is pinned by test, not assumed.

## Attribution

The dirty-flag layout tree lineage traces to CitizenOneX's `base_layout.lua`
(~510 lines, unpackaged in `simple_brilliant_app/example/layout/`). Credit
explicitly on adoption. He also shipped the emulator's circular safe-area
overlay. He is a collaborator to invite, not a competitor to route around.

## Adjacent projects — the layer below, not rivals

- **xg-glass-sdk** (hkust-spark): Kotlin Multiplatform device-access
  abstraction across Rokid, Meta Ray-Ban, Frame, RayNeo, Even Realities G1,
  INMO, Omi. Includes a simulator. Plumbing we could render onto.
- **Extentos**: multi-vendor glasses dev platform, in development.

Two independent groups building cross-vendor plumbing is evidence the
device-agnostic boundary is the right bet.

## Naming

Package name is `glanceable`. `peripheral` was taken on PyPI. `Parallax` was
considered and set aside: in near-eye display work parallax is the *artifact*
being engineered out, and Halo's display is monocular, so no parallax exists
on the device. To rename, change the `src/glanceable/` directory, the
`[project] name` in `pyproject.toml`, and the imports in `tests/` and
`examples/`.

`Paradox` was also considered and rejected: no semantic relationship to round
displays, and it collides with Paradox Interactive and Paradox.ai, both active
software companies with strong search presence.
