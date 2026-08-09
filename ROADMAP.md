# Roadmap

Ordered by what removes the most risk, not by what is most fun. "Risk" here
means one specific thing: **if we are wrong about this, how much work above it
has to be redone?** That is why validating the abstraction outranks validating
the device, and why polish comes after both.

Shipped work is not listed here — see [CHANGELOG.md](CHANGELOG.md). As of v0.2
that is the chord solver and typography layer, the `Surface` boundary, and
`glanceable.markdown` with its vault corpus.

## Prove the bet

1. [ ] **A second, non-Brilliant backend.** The device-agnostic boundary is the
   entire strategic claim — "a library that renders on one vendor's panel is an
   accessory; one that renders anywhere is a standard" — and it is currently
   **untested**. `PILSurface` and `SpriteSurface` were written by one author
   against one mental model, which is not independent evidence that the
   `Surface` ABC is the right three verbs. If it is wrong, every module above
   `surface.py` needs rework.

   Candidate substrates: **xg-glass-sdk** (Kotlin Multiplatform, spans Rokid,
   Meta Ray-Ban, Frame, RayNeo, Even Realities G1, INMO, Omi) and **Extentos**.
   xg-glass-sdk ships a simulator, so this needs **no hardware** — which makes
   it both the higher-value and the cheaper of the two validations below it.

2. [ ] **Run on a physical Halo.** Confirm or correct `SpriteSurface`'s wire
   format. Three things are unresolved and cannot be settled by reading the SDK:
   whether `x`/`y` are 0- or 1-based (we emit 0-based; the SDK documents 1..640,
   which is Frame's stale bound), whether the device accepts the sprite/coords
   ordering as sent, and whether `code` allocation collides with anything the
   firmware reserves.

3. [ ] **Device-side Lua counterpart** with dirty-rect tracking, validated
   against the emulator's PIL framebuffer. Lineage traces to CitizenOneX's
   `base_layout.lua`; credit explicitly on adoption.

## Fix what a user hits today

4. [ ] **Ship or find a CJK-capable face.** DejaVu Sans — what
   `find_system_font()` usually picks — has **no CJK glyphs at all**, so a
   Japanese note renders entirely as tofu. `metadata.unrenderable` already
   reports every character, so nothing is silent; what is missing is CJK faces
   in the `CANDIDATES` search path and a louder signal than a metadata field.
   Cheap, and the most visible defect in the repo.

5. [ ] **Dictionary line breaking.** Even with a CJK face, a spaceless run is
   treated as one long word and hyphen-broken on meaningless boundaries. Text
   is conserved; the breaks are wrong. Needs UAX #14 line-break classes.

6. [ ] **Widow control at page boundaries.** A heading or a lone list item can
   strand alone on a page. Worse: a code block starting on the *last* line of a
   page gets a one-slot sub-viewport, so it takes the narrowest chord on the
   panel and breaks at roughly fifteen characters.

7. [ ] **Real alpha blending in `blit_coverage`.** It writes palette indices
   rather than blending, so text is correct only over a background matching
   `palette_base`. Render on black until this lands.

## Build on top — once the layer is trusted

8. [ ] **Five primitives**: Glance, Stat, Ticker, Prompt, ShortList. **Five,
   not forty.** *Gated on item 2:* CLAUDE.md is explicit that widgets do not
   get added until the text layer is validated on hardware. Listing them any
   higher would contradict a hard rule.

9. [ ] **Point the bridge at a live vault server, and at a real vault.**
   `examples/vault/` is synthetic, so it only contains mess someone thought to
   invent — and it still found two defects the unit fixtures missed. A real
   vault will find more.

10. [ ] **Glyph atlas caching**: rasterize once, ship once, cache on device.
    *Demoted* — it is a BLE bandwidth optimisation and there is no BLE
    transport yet, so today it optimises a path that does not exist.

11. [ ] **Shaping and BiDi.** Genuinely large. `advance()` is a per-string
    `getlength`, which is wrong for any script needing contextual shaping.

12. [ ] **Written legibility guide** with measured contrast floors for the panel
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
