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
   path does.

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
