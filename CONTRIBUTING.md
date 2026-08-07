# Contributing

Read [CLAUDE.md](CLAUDE.md) first. It carries the hard rules and the list of
bugs already fixed, so you do not reintroduce them.

## Setup

```bash
pip install -e ".[dev]"
pytest -q          # 20 passed
```

## The bar

- **Every behavioural change needs a test**, named after the behaviour.
  Regression tests are named after the bug they pin.
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
5. Non-Latin support: shaping, BiDi. Currently Latin only.

## Prior art and credit

The dirty-flag layout tree lineage traces to CitizenOneX's `base_layout.lua`.
If you extend that part, keep the attribution. Credit is cheap and this
ecosystem is small.
