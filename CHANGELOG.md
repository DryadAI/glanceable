# Changelog

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
