# Roadmap

Ordered by what removes the most risk, not by what is most fun. "Risk" here
means one specific thing: **if we are wrong about this, how much work above it
has to be redone?** That is why validating the abstraction outranks validating
the device, and why polish comes after both.

Shipped work is not listed here — see [CHANGELOG.md](CHANGELOG.md). As of v0.2
that is the chord solver and typography layer, the `Surface` boundary, and
`glanceable.markdown` with its vault corpus.

## Prove the bet

1. [~] **A second, non-Brilliant backend.** Partly done, and the finding
   changed the item.

   `xg-glass-sdk` cannot supply the evidence this item wants. Its display API
   is `display(text: String)` and `displayImage(png_bytes)` — whole frames, not
   draw ops — so a backend for it is `PILSurface.to_rgb()` plus an encode and
   exercises nothing about whether `fill_rect`/`blit_coverage`/`present` are
   the right three verbs. Its simulator is an Android Emulator running a Kotlin
   app: "no hardware" is true, but it needs JDK, Gradle and adb rather than
   Python. Likely the same for Extentos. **This is itself informative** — the
   portable interface across vendors is a finished frame. Op-level drawing is
   the exception, exposed by Halo and Frame because BLE bandwidth makes
   whole-frame updates expensive.

   `MonoSurface` (`src/glanceable/mono.py`) attacks from the direction that
   actually hurts: a 1-bit panel with **no palette at all**, which is what
   SSD1306, SH1106 and most e-paper are. Result: **the three verbs survive.**
   `render_text` and `render_markdown` run unmodified, the chord invariant
   holds, and `RetainedSurface` composes with a backend written after it.

   **The parameters do not.** `palette_base` and `levels` are Halo's colour
   model leaking into an otherwise general signature — now the second
   independent line of evidence, alongside `SpriteSurface` raising on a
   non-zero base.

   Still open: a backend by a *different author*, which neither `MonoSurface`
   nor `SpriteSurface` can supply. `MonoSurface` is a host-side PIL target, not
   a device driver — pointing it at real `luma.oled` or e-paper hardware would
   close that, and the board costs about ten dollars.

2. [ ] **Run on a physical Halo.** Narrower than it was. The wire format now
   round-trips through `halo-emulator`: glanceable's bytes go through
   Brilliant's own `sprite.lua` and render pixel-identical to `PILSurface`,
   which exercises header layout, palette mapping, bit packing,
   transparent-index-0 and the origin together. That settled the 0-vs-1-based
   question empirically — we were emitting 0-based, every sprite landed one
   pixel up and left, and output matched only after shifting (+1, +1).

   What a device is still for: emulator fidelity where it is known to drift (it
   low-clamps `circle` and `polygon`; `lua_display.c` does not), whether `code`
   allocation collides with anything the firmware reserves, real BLE throughput
   and MTU behaviour under load, and whether a damaged-region update actually
   reads as *still* on glass rather than merely smaller.

3. [ ] **Replace the palette parameters with a colour policy, or drop them.**
   Two unrelated backends now fail on `palette_base` for unrelated reasons:
   `SpriteSurface` raises because the index cannot survive bit-depth masking on
   pack; `MonoSurface` cannot honour it because a 1-bit panel has no palette.
   Two failures, one cause — Halo's colour model sits in a signature that is
   otherwise general, and `blit_coverage` is the only place the ABC is not
   uniform. The shape that would work is a surface advertising what it can
   express, rather than two palette parameters threaded through every call.
   Decide before 1.0; it is a public signature.

4. [ ] **Device-side Lua counterpart** with dirty-rect tracking, validated
   against the emulator's PIL framebuffer. Lineage traces to CitizenOneX's
   `base_layout.lua`; credit explicitly on adoption.

## Fix what a user hits today

5. [ ] **Ship or find a CJK-capable face.** DejaVu Sans — what
   `find_system_font()` usually picks — has **no CJK glyphs at all**, so a
   Japanese note renders entirely as tofu. `metadata.unrenderable` already
   reports every character, so nothing is silent; what is missing is CJK faces
   in the `CANDIDATES` search path and a louder signal than a metadata field.
   Cheap, and the most visible defect in the repo.

6. [ ] **Dictionary line breaking.** Even with a CJK face, a spaceless run is
   treated as one long word and hyphen-broken on meaningless boundaries. Text
   is conserved; the breaks are wrong. Needs UAX #14 line-break classes.

7. [ ] **Widow control at page boundaries.** A heading or a lone list item can
   strand alone on a page. Worse: a code block starting on the *last* line of a
   page gets a one-slot sub-viewport, so it takes the narrowest chord on the
   panel and breaks at roughly fifteen characters.

8. [ ] **Real alpha blending in `blit_coverage`.** It writes palette indices
   rather than blending, so text is correct only over a background matching
   `palette_base`. Render on black until this lands.

## Build on top — once the layer is trusted

9. [ ] **Five primitives**: Glance, Stat, Ticker, Prompt, ShortList. **Five,
   not forty.** *Gated on item 2:* CLAUDE.md is explicit that widgets do not
   get added until the text layer is validated on hardware. Listing them any
   higher would contradict a hard rule.

10. [ ] **Point the bridge at a live vault server, and at a real vault.**
   `examples/vault/` is synthetic, so it only contains mess someone thought to
   invent — and it still found two defects the unit fixtures missed. A real
   vault will find more.

11. [ ] **Glyph atlas caching**: rasterize once, ship once, cache on device.
    *Demoted* — it is a BLE bandwidth optimisation and there is no BLE
    transport yet, so today it optimises a path that does not exist.

12. [ ] **Shaping and BiDi.** Genuinely large. `advance()` is a per-string
    `getlength`, which is wrong for any script needing contextual shaping.

13. [ ] **Written legibility guide** with measured contrast floors for the panel
    in daylight, and saccade-budget guidance.

## Not planned

- **Animation.** See CLAUDE.md rule 2. A deliberate omission, not a gap.
- **A widget kitchen sink.** The value is the layer everything sits on, not
  breadth of components.
- **A note-taking product.** `markdown.py` renders markdown; it does not know
  what Obsidian is, and wikilinks are the only vault-flavoured thing allowed in
  — because they are cheap and CommonMark-adjacent.
- **Retrieval.** Fetching notes is solved and commoditised. Any bridge consumes
  an existing server; it does not implement search.
- **Golden-image CI against the emulator.** *Dropped.* Redundant with the golden
  invariant already in the suite — no lit pixel may fall outside the safe radius
  — which survives font upgrades and distro differences where an image checksum
  would not. Re-open only if a defect turns up that the invariant cannot
  express.

## Open questions, not being solved yet

Named so they are not mistaken for oversights: BLE transport for a paginated
document, phone↔desktop relay topology, and sync. All out of scope until the
wire format is confirmed on hardware (item 2).
