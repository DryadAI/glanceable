# Changelog

## 0.2.0 — unreleased

`glanceable.markdown`: markdown → circular display. Still host-side only;
**never run on hardware.** 235 tests pass on Python 3.10, 3.12 and 3.14.

### Added
- `parse_markdown(source, policy) -> MarkdownDoc` — pure, needs no font or
  display, so one parse can be laid out against several faces and panels.
- `layout_markdown(source, display, font, *, page=0, ...) -> MarkdownLayout` —
  pagination as a discrete index and a pure function of its inputs. No cursor,
  no scroll, no auto-advance.
- `render_markdown(surface, source, font, ...)` — mirrors `render_text`.
  `MarkdownLayout` exposes `.runs` / `.leftover` / `.truncated` with `Layout`'s
  meanings, so the existing blit loop works on it unchanged.
- `Metadata`: frontmatter (raw, plus a flat scan that is **not** YAML),
  wikilink targets, links, footnote definitions, dropped elements, table
  reformatting notes, and characters the loaded face cannot draw.
- `Policy` — every degradation knob in one frozen dataclass.
- `usable_lines()`, stricter than `Font.max_feasible_lines`, whose 24px floor is
  about four characters and unusable once a block also carries an indent.
- `has_glyph()` — PIL draws an uncovered character as an often-invisible
  `.notdef` and raises nothing, so markers are checked before use.
- Optional extra `glanceable[markdown]` (markdown-it-py). Core stays
  Pillow-only; a missing extra raises `MarkdownDependencyError`.
- Fixture corpus of deliberately ugly markdown, and a corpus-level test that
  every word of source reaches the glass, `leftover_source`, or `metadata`.

- `examples/obsidian_bridge.py` and `examples/vault/` — a vault-directory
  renderer and a committed corpus of deliberately ugly notes, pinned by
  `tests/test_vault_corpus.py`. Not part of the package; nothing in
  `glanceable/` imports it, and `markdown.py` knows nothing about Obsidian.
  Retrieval is deliberately a trivial substring match, there to be replaced.

### Fixed
- **Split list items lost their marker.** A list item straddling a page
  boundary dropped its prefix from the remainder, so the continuation rendered
  as unmarked text. It now repeats — on a HUD there is no scrollback, so each
  page has to stand alone. Found by the vault corpus; the invented fixtures
  never split a list item.
- **`leftover_source` did not round-trip for a split list item.** `_resynth`
  reused the *rendered* marker, so a split bullet came back as the literal
  `• text`, which re-parses as a paragraph rather than a list item and silently
  changed the block kind on the resumed page.
- **Callout bodies could not round-trip.** There is no markdown for "blockquote
  continuation with no marker", so a bare body came back as a centred
  paragraph. Bodies now carry the quote marker, which also ties them visually
  to their label.
- **Docs**: `SpriteOp` was still documented with its pre-0.1 flat shape. The
  `getting-started` device example used `op.palette_data` / `op.pixel_data`,
  which have not existed since the sprite/coords split and would raise
  `AttributeError`. Both corrected against the shipped source.

### Known limitations
- CJK is conserved but hyphen-broken on the wrong boundaries.
- No widow control at page boundaries.
- Left-aligned blocks have a ragged left edge near the poles; code blocks do
  not, because they get a rectangular sub-viewport.

## 0.1.0 — unreleased

First cut. Host-side only; **never run on hardware.**

### Added
- `CircularDisplay` chord solver, constrained by the line-box edge farther
  from the equator rather than its midpoint.
- `Font` with face-derived metrics, chord-aware word wrap, hyphenation of
  over-wide words, and N-level coverage quantization.
- `Layout` with `leftover` / `truncated`, so text is never silently cut.
- `Surface` ABC with `PILSurface` and `SpriteSurface` backends.
- 20 tests, including a golden invariant that no lit pixel falls outside the
  safe radius.

### Fixed during pre-release audit
- Silent blank screen when `line_height × max_lines` exceeded the panel.
- Text silently dropped when a word could not be hyphenated to fit.
- Non-terminating re-centring (oscillated 5→6→5 rather than converging).
- A surface-agreement test that could not fail.

### Deliberately omitted
- Animation. See CLAUDE.md rule 2.
