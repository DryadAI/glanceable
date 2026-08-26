"""Round-trip glanceable's sprite output through Brilliant's Halo emulator.

The wire format was previously verified only by field-shape comparison against
`brilliant_msg`. This drives the actual bytes through Brilliant's own device
Lua and renders them, then compares against `PILSurface` pixel-for-pixel.

Path under test::

    SpriteSurface -> SpritePayload -> TxSprite.pack()
        -> Lua string -> sprite.lua parse_sprite / set_palette
        -> frame.display.bitmap -> emulator framebuffer

The emulator states it "mirrors Halo firmware 0.8.8 (modules/halo/src/
lua_display.c)" and implements the 1-based low-clamp on every primitive.

**This is evidence, not proof.** The emulator is Brilliant's model of the
firmware, not silicon, and it diverges from the source in at least one place:
it low-clamps `circle` and `polygon`, which `lua_display.c` does not. Anything
established here is "validated against the emulator" per hard rule 3.

Requires the dev extras (`lupa`, `halo-emulator`, `brilliant-msg`); skipped
when absent so the core suite stays Pillow-only per hard rule 6.
"""

import dataclasses
import pathlib
import shutil
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from glanceable import (  # noqa: E402
    HALO,
    Font,
    PILSurface,
    SpriteSurface,
    find_system_font,
    ramp_palette,
    render_text,
)

pytest.importorskip("lupa", reason="emulator round-trip needs the dev extras")
halo_emulator = pytest.importorskip("halo_emulator")
brilliant_msg = pytest.importorskip("brilliant_msg")

from brilliant_msg import TxSprite  # noqa: E402
from halo_emulator import HaloEmulator  # noqa: E402

FONT = find_system_font()
TEXT = "Cmaj7 to Fmaj7 then G7 resolving home"
LEVELS = 4


@pytest.fixture
def emulator(tmp_path):
    """An emulator with Brilliant's own sprite.lua loaded."""
    import importlib.resources as resources

    lua_dir = resources.files("brilliant_msg") / "lua"
    for name in ("sprite.lua", "sprite_coords.lua"):
        shutil.copy(str(lua_dir / name), tmp_path / name)

    emu = HaloEmulator(sandbox_dir=tmp_path, print_handler=None)
    emu.connect()
    emu.execute_lua("sprite = require('sprite')")
    try:
        yield emu
    finally:
        emu.stop()


def _draw(emu, packed: bytes, x: int, y: int) -> None:
    """Feed one payload through sprite.lua exactly as a device app would.

    x/y go in untouched, so whatever origin SpriteSurface emits is what gets
    tested -- the emulator applies the firmware's clamp-then-subtract itself.
    """
    g = emu._lua.globals()
    g["_payload"], g["_x"], g["_y"] = packed, x, y
    emu.execute_lua(
        """
        local spr = sprite.parse_sprite(_payload)
        sprite.set_palette(spr.num_colors, spr.palette_data)
        frame.display.bitmap(_x, _y, spr.width, 2 ^ spr.bpp, 0, spr.pixel_data)
        """
    )


def _render_both(emu):
    palette = ramp_palette(LEVELS)
    font = Font(FONT, 13)

    reference = PILSurface(256, 256, palette)
    render_text(reference, font, TEXT, HALO, max_lines=5, levels=LEVELS)

    sprites = SpriteSurface(256, 256, palette)
    render_text(sprites, font, TEXT, HALO, max_lines=5, levels=LEVELS)
    for op in sprites.ops:
        _draw(emu, TxSprite(**dataclasses.asdict(op.payload)).pack(), op.coords.x, op.coords.y)

    return reference.to_rgb(), emu.get_framebuffer().convert("RGB"), sprites


def test_emulator_render_matches_pil_surface_exactly(emulator):
    """End-to-end: header layout, palette mapping, bit packing and origin.

    A byte-level error would not produce a near-match -- it would produce
    garbage -- so an exact match exercises the whole chain at once.
    """
    reference, actual, _ = _render_both(emulator)
    assert list(reference.getdata()) == list(actual.getdata())


def test_sprite_coords_are_one_based(emulator):
    """Every Halo display primitive does `if (v < 1) v = 1; v -= 1;`.

    Emitting 0-based coords put every sprite one pixel up and left. The
    emulator round-trip caught it: output matched the reference only after
    shifting (+1, +1). Pinned here so it cannot silently regress.
    """
    palette = ramp_palette(LEVELS)
    sprites = SpriteSurface(256, 256, palette)
    reference = PILSurface(256, 256, palette)
    font = Font(FONT, 13)

    render_text(sprites, font, TEXT, HALO, max_lines=5, levels=LEVELS)
    render_text(reference, font, TEXT, HALO, max_lines=5, levels=LEVELS)

    for pil_op, sprite_op in zip(reference.ops, sprites.ops):
        assert sprite_op.coords.x == pil_op[0] + 1
        assert sprite_op.coords.y == pil_op[1] + 1


def test_zero_origin_would_shift_the_frame(emulator):
    """Guards the guard: confirm the emulator is actually sensitive to origin.

    If this passed regardless of coordinates, the round-trip test above would
    prove nothing about the origin at all.
    """
    palette = ramp_palette(LEVELS)
    font = Font(FONT, 13)

    reference = PILSurface(256, 256, palette)
    render_text(reference, font, TEXT, HALO, max_lines=5, levels=LEVELS)

    sprites = SpriteSurface(256, 256, palette)
    render_text(sprites, font, TEXT, HALO, max_lines=5, levels=LEVELS)
    for op in sprites.ops:
        # deliberately wrong: undo the 1-based conversion
        _draw(
            emulator,
            TxSprite(**dataclasses.asdict(op.payload)).pack(),
            op.coords.x - 1,
            op.coords.y - 1,
        )

    shifted = emulator.get_framebuffer().convert("RGB")
    assert list(reference.to_rgb().getdata()) != list(shifted.getdata())


def test_palette_base_is_refused_rather_than_silently_collapsed():
    """`palette_base` cannot survive the sprite path.

    `TxSprite.pack()` masks each pixel index to the declared bit depth, so at
    levels=4 (2bpp) base=4 sends index 7 and base=12 sends 15, and both arrive
    as 3 -- every base produces identical bytes. PILSurface honours the base,
    so the two backends disagreed silently, and the op-geometry comparison
    could not see it because it compares only (x, y, w, h).
    """
    from PIL import Image

    surface = SpriteSurface(256, 256, ramp_palette(LEVELS))
    coverage = Image.new("L", (16, 8), 255)

    surface.blit_coverage(coverage, 0, 0, 0, LEVELS)  # base 0 is fine

    with pytest.raises(ValueError, match="palette_base"):
        surface.blit_coverage(coverage, 0, 0, 4, LEVELS)


def test_markdown_round_trips_through_the_emulator(emulator):
    """The markdown layer has 215 host-side tests and had never reached a
    device path. It drives many more blits than render_text, across two faces
    when emphasis_font is set."""
    from glanceable.markdown import render_markdown

    palette = ramp_palette(LEVELS)
    font = Font(FONT, 13)
    source = (
        "# Chord chart\n\n"
        "Play **Cmaj7** then Fmaj7.\n\n"
        "- resolve to G7\n"
        "- repeat twice\n"
    )

    reference = PILSurface(256, 256, palette)
    render_markdown(reference, source, font, HALO, levels=LEVELS)

    sprites = SpriteSurface(256, 256, palette)
    render_markdown(sprites, source, font, HALO, levels=LEVELS)
    assert sprites.ops, "markdown produced no sprites"

    for op in sprites.ops:
        _draw(emulator, TxSprite(**dataclasses.asdict(op.payload)).pack(),
              op.coords.x, op.coords.y)

    assert list(reference.to_rgb().getdata()) == list(
        emulator.get_framebuffer().convert("RGB").getdata()
    )
