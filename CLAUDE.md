# CLAUDE.md

Context for any AI assistant or new contributor working on this repo. Read
this before writing code. It exists because a parallel brainstorming session,
lacking this context, produced 800 lines of unverified widgets under a
different name with an animation framework that contradicts the core design
principle. Constraints belong in the repo, not in one conversation's memory.

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
| `typography.py` | geometry | metrics, chord-aware wrap, rasterization |
| `fonts.py` | — | cross-platform face discovery |
| `render.py` | all of the above | `render_text` convenience |
| `markdown.py` | typography, geometry, surface | markdown → circular display |

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

Established by reading `brilliant-msg` 7.0.0 from PyPI, not from memory:

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
  the color names, Halo indexes are 0-15". 16-colour palettes work.

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

- **Never run on hardware.** `SpriteSurface` emits against published
  `brilliant_msg` 7.0.0 shapes but has not been round-tripped on a physical
  Halo. Treat the wire format as unconfirmed.
- No device-side Lua counterpart yet.
- `blit_coverage` writes palette indices rather than alpha-blending, so it is
  correct only over a background matching `palette_base`.
- Latin only. `advance()` is a per-string `getlength`, wrong for any script
  needing contextual shaping. No BiDi.
- No glyph atlas caching; every run rasterizes fresh.

`markdown.py` specifically — host-side tested (215 of the suite's 235 tests cover
it: 187 unit plus 28 over the vault corpus, on 3.10, 3.12 and 3.14), never seen
by a device:

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
