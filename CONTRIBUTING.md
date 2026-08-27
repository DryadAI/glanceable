# Contributing

Read [CLAUDE.md](CLAUDE.md) first. It carries the hard rules and the list of
bugs already fixed, so you do not reintroduce them.

## Setup

```bash
pip install -e ".[dev]"
pytest -q          # 273 passed  (268 + 1 skip without dev extras)
```

**The dev extras do not install on Python 3.14.** `brilliant-msg` requires
`brilliant-ble`, which pins `bleak<1.0.0`, and no `bleak` below 1.0 supports
3.14 — the resolver fails with `No matching distribution found for
bleak<1.0.0,>=0.22.3`. It is a transitive pin two levels down, so there is
nothing to do here but wait for it. Use 3.10-3.13 for the full 273; the 273
figure above was measured on CPython 3.12.13.

The core suite is Pillow-only and runs on every supported version, 3.14
included, giving 268 passed plus 1 skip — the skip is
`tests/test_emulator_roundtrip.py`, which needs the extras. Nothing outside
that file depends on them.

## The bar

- **Every behavioural change needs a test**, named after the behaviour.
  Regression tests are named after the bug they pin — and **check that the test
  fails without the fix.** Revert the change, run the one test, confirm it goes
  red, restore. Two tests in this repo silently stopped discriminating after
  unrelated changes; a test that passes either way is worse than no test,
  because it reads as coverage.
- **Render it and look at it.** A contact sheet of rendered pages has caught
  defects the suite did not, including a fixture that had quietly stopped
  exercising the code path it was named for.
- **Never claim verification that has not happened.** If you have not run it on
  hardware, say so in the PR. Overclaiming costs this project more than a
  missing feature does.
- **No animation.** See CLAUDE.md rule 2. This is a design decision.
- **No device-specific calls above `surface.py`.** If you need a new drawing
  primitive, add it to the `Surface` ABC and implement it in all backends.

## Most valuable contributions right now

1. **Run it on a physical Halo** and report whether `SpriteSurface`'s output
   renders. The wire format is unconfirmed and this is the biggest open risk.
2. Device-side Lua counterpart, validated against the emulator framebuffer.
3. Glyph atlas caching — currently every run rasterizes fresh, which is fine
   host-side and wasteful over BLE.
4. Real alpha blending in `blit_coverage`.
5. Non-Latin support: shaping, BiDi, and dictionary line breaking. CJK is
   currently conserved but broken on meaningless boundaries.
6. Point `examples/obsidian_bridge.py` at a *real* vault and report what breaks.
   `examples/vault/` is synthetic, so it only contains mess someone thought to
   invent — and it still found two defects the unit fixtures missed.

## Prior art and credit

The dirty-flag layout tree lineage traces to CitizenOneX's `base_layout.lua`.
If you extend that part, keep the attribution. Credit is cheap and this
ecosystem is small.
