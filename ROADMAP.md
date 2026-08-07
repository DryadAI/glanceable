# Roadmap

Ordered by what removes the most risk, not by what is most fun.

## Now — validate

- [ ] **Run on a physical Halo.** Confirm or correct `SpriteSurface`'s wire
      format. Everything below is speculative until this is done.
- [ ] Device-side Lua counterpart with dirty-rect tracking, validated against
      the emulator's PIL framebuffer.
- [ ] Golden-image CI against the emulator.

## Next — make it cheap to use

- [ ] Glyph atlas caching: rasterize once, ship once, cache on device.
      Currently every run rasterizes fresh — wasteful over BLE.
- [ ] Real alpha blending in `blit_coverage`.
- [ ] A small set of primitives on top of the text layer: Glance, Stat,
      Ticker, Prompt, ShortList. **Five, not forty.**

## Later — make it a standard

- [ ] Second non-Brilliant backend. The day this renders on another vendor's
      panel it stops being an accessory. Candidate substrates: xg-glass-sdk,
      Extentos.
- [ ] Non-Latin: shaping, BiDi.
- [ ] Written legibility guide with measured contrast floors for the panel in
      daylight, and saccade-budget guidance.

## Not planned

- **Animation.** See CLAUDE.md rule 2.
- **A widget kitchen sink.** The value is the layer everything sits on, not
  breadth of components.
