"""Sprite wire-format and retained-mode tests.

The wire-format tests encode facts verified against brilliant_msg 7.1.1 source
(tx_sprite.py, tx_sprite_coords.py, lua/sprite.lua). They are the guardrail
that stops a future edit from silently desynchronising the device parser.
"""

import dataclasses

import pytest
from PIL import Image

from glanceable.retained import RetainedSurface
from glanceable.surface import (
    PILSurface,
    SpriteCoords,
    SpritePayload,
    SpriteSurface,
    Surface,
)
from glanceable.typography import ramp_palette

PALETTE = ramp_palette(4)


def coverage(w, h, value=255):
    return Image.new("L", (w, h), value)


# -- wire format against brilliant_msg 7.1.1 ------------------------------


def test_payload_fields_match_txsprite_exactly():
    """TxSprite(**asdict(payload)) must construct without translation."""
    assert [f.name for f in dataclasses.fields(SpritePayload)] == [
        "width",
        "height",
        "num_colors",
        "palette_data",
        "pixel_data",
        "compress",
    ]


def test_coords_fields_match_txspritecoords_exactly():
    assert [f.name for f in dataclasses.fields(SpriteCoords)] == [
        "code",
        "x",
        "y",
        "offset",
    ]


def test_compress_defaults_false():
    """The compressed flag is header byte 5; sprite.lua reads it positionally."""
    assert SpritePayload(1, 1, 2, b"", b"").compress is False


def test_palette_length_always_matches_the_declared_colour_count():
    """sprite.lua slices exactly num_colors*3 bytes and treats the rest as
    pixels, so any mismatch shifts every pixel in the frame."""
    for levels in (2, 4, 16):
        s = SpriteSurface(256, 256, ramp_palette(levels))
        assert len(s._palette) == s._num_colors * 3


def test_palette_is_padded_up_to_the_bucket_not_left_short():
    """A 5-colour ramp rounds up to the 16-colour format; the wire palette must
    still be 48 bytes or the device parser reads pixels as palette."""
    s = SpriteSurface(256, 256, ramp_palette(5))
    assert s._num_colors == 16
    assert len(s._palette) == 48


def test_num_colors_is_rounded_to_a_format_the_packer_supports():
    """TxSprite.pack() buckets bpp as <=2, <=4, else 4bpp."""
    assert SpriteSurface(64, 64, ramp_palette(2))._num_colors == 2
    assert SpriteSurface(64, 64, ramp_palette(4))._num_colors == 4
    assert SpriteSurface(64, 64, ramp_palette(16))._num_colors == 16


def test_oversized_palette_is_rejected():
    with pytest.raises(ValueError, match="caps at 16"):
        SpriteSurface(64, 64, [0] * (17 * 3))


def test_sprite_codes_do_not_collide_before_wrapping():
    """Previously derived from len(ops), which never resets, so codes ran past
    0xFF and collided with sprites still live on the device."""
    s = SpriteSurface(256, 256, PALETTE, base_code=0x20)
    codes = [s._next_code() for _ in range(0x100 - 0x20)]
    assert len(set(codes)) == len(codes)


def test_sprite_codes_wrap_back_to_base_not_to_zero():
    s = SpriteSurface(256, 256, PALETTE, base_code=0x20)
    codes = [s._next_code() for _ in range(0x100 - 0x20 + 1)]
    assert codes[-1] == 0x20


def test_reset_codes_restarts_allocation():
    s = SpriteSurface(256, 256, PALETTE)
    first = s._next_code()
    s._next_code()
    s.reset_codes()
    assert s._next_code() == first


def test_pixel_data_stays_one_byte_per_pixel():
    """TxSprite.pack() does the bit packing; pre-packing would double-encode."""
    s = SpriteSurface(256, 256, PALETTE)
    s.fill_rect(0, 0, 4, 3, 1)
    assert len(s.ops[0].payload.pixel_data) == 12


# -- retained mode over both backends -------------------------------------


def test_retained_works_over_the_sprite_backend():
    inner = SpriteSurface(256, 256, PALETTE)
    s = RetainedSurface(inner)
    cov = coverage(120, 18)

    s.blit_coverage(cov, 20, 100, 0, 4)
    s.present()
    after_first = len(inner.ops)

    s.blit_coverage(cov, 20, 100, 0, 4)
    s.present()

    assert len(inner.ops) == after_first, "an unchanged frame must emit no sprites"


def test_retained_erases_the_previous_extent_on_the_sprite_backend():
    inner = SpriteSurface(256, 256, PALETTE)
    s = RetainedSurface(inner)

    s.blit_coverage(coverage(200, 18), 20, 100, 0, 4)
    s.present()
    inner.ops.clear()

    s.blit_coverage(coverage(80, 18), 20, 100, 0, 4)
    s.present()

    assert any(op.width >= 200 for op in inner.ops), "old extent must be covered"


def test_retained_only_touches_the_changed_line():
    inner = SpriteSurface(256, 256, PALETTE)
    s = RetainedSurface(inner)
    for i in range(5):
        s.blit_coverage(coverage(200, 18), 20, 40 + i * 20, 0, 4)
    s.present()
    inner.ops.clear()

    for i in range(5):
        s.blit_coverage(coverage(200, 18, 128 if i == 2 else 255), 20, 40 + i * 20, 0, 4)
    s.present()

    assert len(inner.ops) < 5


def test_both_backends_agree_on_op_geometry():
    """The surface-agreement property: identical calls, identical extents."""
    pil, spr = PILSurface(256, 256, PALETTE), SpriteSurface(256, 256, PALETTE)
    for surface in (pil, spr):
        s = RetainedSurface(surface)
        s.fill_rect(10, 10, 40, 20, 1)
        s.blit_coverage(coverage(64, 18), 12, 40, 0, 4)
        s.present()

    assert [(o[0], o[1], o[2], o[3]) for o in pil.ops] == [
        (o.x, o.y, o.width, o.height) for o in spr.ops
    ]


def test_retained_surface_satisfies_the_abc():
    assert isinstance(RetainedSurface(PILSurface(64, 64, PALETTE)), Surface)
