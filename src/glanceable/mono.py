"""A 1-bit monochrome backend, written to stress the `Surface` ABC.

ROADMAP item 1 wants independent evidence that `Surface` is the right three
verbs. `xg-glass-sdk` cannot supply it: its display API is `display(text)` and
`displayImage(png_bytes)` -- whole frames, not draw ops -- so a backend for it
is `PILSurface.to_rgb()` plus an encode, exercising nothing about the op-level
design. Its simulator is an Android Emulator, not a Python target.

This backend attacks the ABC from the direction that actually hurts: a panel
with **no palette at all**. SSD1306, SH1106 and most e-paper are 1 bit per
pixel -- a pixel is lit or it isn't. Two of `blit_coverage`'s five parameters
have no meaning here, which is exactly the pressure that reveals whether the
signature is general or whether it encoded Halo's palette model by accident.

Not a device driver. It renders to a PIL 1-bit image so the ABC can be
exercised host-side; a real `luma.oled` or e-paper driver would swap the
backing store and keep everything else.
"""

from __future__ import annotations

from PIL import Image

from .surface import Surface


class MonoSurface(Surface):
    """A 1-bit surface. Lit or unlit; no palette, no ramp.

    Args:
        threshold: coverage at or above this (0-255) lights the pixel.
            Antialiasing cannot survive 1 bit, so where the ramp lands is a
            policy choice the caller should own rather than a constant.
    """

    def __init__(self, width: int, height: int, threshold: int = 128):
        self._img = Image.new("1", (width, height), 0)
        self._size = (width, height)
        self._threshold = threshold
        self.dirty: list[tuple[int, int, int, int]] = []
        self.ops: list[tuple[int, int, int, int]] = []
        #: Parameters the ABC requires but this device cannot honour. Recorded
        #: rather than ignored -- see the note at the bottom of this module.
        self.discarded: list[str] = []

    @property
    def size(self) -> tuple[int, int]:
        return self._size

    def fill_rect(self, x: int, y: int, w: int, h: int, color_index: int) -> None:
        """`color_index` collapses to on/off.

        A palette index has no meaning on a 1-bit panel. Index 0 is background
        in `ramp_palette`, so 0 clears and anything else lights -- a convention
        this backend has to invent, which the ABC does not specify.
        """
        if w <= 0 or h <= 0:
            return
        value = 0 if color_index == 0 else 1
        self._img.paste(value, (x, y, x + w, y + h))
        self.dirty.append((x, y, w, h))
        self.ops.append((x, y, w, h))

    def blit_coverage(
        self, coverage: Image.Image, x: int, y: int, palette_base: int, levels: int
    ) -> None:
        """Threshold the coverage map. `palette_base` and `levels` are dead.

        `levels` describes how finely the ramp was quantised, which is
        irrelevant once everything collapses to one bit. `palette_base` names a
        palette that does not exist. Both are accepted because the ABC requires
        them, and both are recorded in `discarded` rather than silently
        swallowed -- hard rule 7 says silent loss has more than one shape, and
        an ignored parameter is one of them.
        """
        if levels != 2:
            self.discarded.append(f"levels={levels} (1-bit panel)")
        if palette_base != 0:
            self.discarded.append(f"palette_base={palette_base} (no palette)")

        mask = coverage.point(lambda p: 255 if p >= self._threshold else 0).convert("1")
        self._img.paste(1, (x, y), mask)
        self.dirty.append((x, y, coverage.width, coverage.height))
        self.ops.append((x, y, coverage.width, coverage.height))

    def present(self) -> None:
        self.dirty.clear()

    def to_rgb(self) -> Image.Image:
        return self._img.convert("RGB")


# What writing this backend showed, recorded here because the finding is the
# point of the exercise rather than the module:
#
# The three verbs survive. `fill_rect`, `blit_coverage` and `present` all map
# onto a panel with a completely different colour model, and nothing above
# `surface.py` needed changing to render markdown onto one. That is real
# evidence for the device-agnostic boundary -- from a direction no Brilliant
# device could have provided.
#
# The *parameters* do not survive. `palette_base` and `levels` are Halo's
# colour model leaking into a signature that is otherwise general, and this is
# the second independent line of evidence for that: `SpriteSurface` already has
# to raise on `palette_base != 0` because the index cannot survive bit-depth
# masking on pack. Two unrelated backends, two different failures, same cause.
#
# The shape that would generalise is a colour policy owned by the surface --
# each backend advertises what it can express and the caller renders to that --
# rather than two palette parameters threaded through every call. That is a
# 1.0 decision, not a patch, and it belongs with ROADMAP item 3.
