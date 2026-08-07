"""The device boundary.

Hard rule for this codebase: nothing above this file may contain a
Halo-specific call. Everything the layout engine knows how to do is expressed
against `Surface`. Three implementations keep that honest -- if a Halo-ism
leaks upward, PILSurface stops matching and the golden tests fail.

This is also the insurance policy. A library that only renders on one vendor's
panel is an accessory to that vendor. One that renders anywhere is a standard.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from PIL import Image


class Surface(ABC):
    """Minimal drawing target. Deliberately tiny -- three verbs."""

    @property
    @abstractmethod
    def size(self) -> tuple[int, int]: ...

    @abstractmethod
    def fill_rect(self, x: int, y: int, w: int, h: int, color_index: int) -> None: ...

    @abstractmethod
    def blit_coverage(
        self, coverage: Image.Image, x: int, y: int, palette_base: int, levels: int
    ) -> None:
        """Composite an L-mode coverage map using palette entries
        [palette_base, palette_base + levels).

        LIMITATION: coverage is written as an index, not alpha-blended. This is
        correct only over a background matching palette entry `palette_base`
        (black, for ramp_palette). Text over a non-black fill will show a halo
        until real blending lands.
        """

    @abstractmethod
    def present(self) -> None:
        """Push the accumulated frame. No double buffer exists on device, so
        implementations are expected to flush only dirty regions."""


class PILSurface(Surface):
    """Host-side surface. Used by the emulator path and by golden tests."""

    def __init__(self, width: int, height: int, palette: list[int]):
        self._img = Image.new("P", (width, height), 0)
        pal = list(palette) + [0] * (768 - len(palette))
        self._img.putpalette(pal)
        self.dirty: list[tuple[int, int, int, int]] = []
        # Full op log, unlike `dirty` which is cleared on present(). Lets the
        # test suite compare what each backend actually received.
        self.ops: list[tuple[int, int, int, int]] = []

    @property
    def size(self) -> tuple[int, int]:
        return self._img.size

    def fill_rect(self, x: int, y: int, w: int, h: int, color_index: int) -> None:
        if w <= 0 or h <= 0:
            return
        self._img.paste(color_index, (x, y, x + w, y + h))
        self.dirty.append((x, y, w, h))
        self.ops.append((x, y, w, h))

    def blit_coverage(
        self, coverage: Image.Image, x: int, y: int, palette_base: int, levels: int
    ) -> None:
        step = 255 / (levels - 1)
        indexed = coverage.point(
            lambda p: palette_base + min(levels - 1, int(round(p / step)))
        )
        mask = coverage.point(lambda p: 255 if p > 0 else 0).convert("1")
        self._img.paste(indexed, (x, y), mask)
        self.dirty.append((x, y, coverage.width, coverage.height))
        self.ops.append((x, y, coverage.width, coverage.height))

    def present(self) -> None:
        self.dirty.clear()

    def to_rgb(self) -> Image.Image:
        return self._img.convert("RGB")


@dataclass
class SpriteOp:
    """One accumulated draw: a pixel payload plus where it goes.

    This maps to *two* messages in brilliant_msg 7.0.0, not one. TxSprite
    carries the pixels and has no position of its own; placement is a separate
    TxSpriteCoords keyed by `code`. Splatting this dataclass into TxSprite
    raises TypeError on `x`. Use `sprite_kwargs()` and `coords_kwargs()`.

    Deliberately imports nothing from brilliant_msg. Keeping the device SDK out
    of the library is exactly what rule 1 in CLAUDE.md protects: the moment
    this module imports a vendor package, PILSurface and SpriteSurface stop
    being interchangeable and the boundary rots.
    """

    width: int
    height: int
    num_colors: int
    palette_data: bytes
    pixel_data: bytes
    x: int
    y: int
    code: int = 0
    compress: bool = False
    offset: int = 0

    def sprite_kwargs(self) -> dict:
        """Exactly the constructor fields of brilliant_msg.TxSprite."""
        return {
            "width": self.width,
            "height": self.height,
            "num_colors": self.num_colors,
            "palette_data": self.palette_data,
            "pixel_data": self.pixel_data,
            "compress": self.compress,
        }

    def coords_kwargs(self) -> dict:
        """Exactly the constructor fields of brilliant_msg.TxSpriteCoords.

        UNCONFIRMED: x/y are emitted 0-based, matching this library's geometry.
        The SDK documents them as 1-based (1..640 -- Frame's panel again, the
        same stale bound as TxPlainText). A one-pixel origin shift will not be
        settled by reading the SDK; it needs a physical Halo.
        """
        return {"code": self.code, "x": self.x, "y": self.y, "offset": self.offset}


class SpriteSurface(Surface):
    """Accumulates ops as TxSprite/TxSpriteCoords payloads for the real device.

    Each op becomes two messages on the wire. `base_code` seeds the per-sprite
    identifier that binds a pixel payload to its placement; codes are unsigned
    bytes, so they wrap at 256. Which codes are safe to use is the application's
    business -- the SDK does not reserve a range.

    NOTE: field shapes are checked against the published brilliant_msg 7.0.0
    classes, but this has NOT been run on hardware. Treat the wire format as
    unconfirmed until it has been round-tripped on a physical Halo.
    """

    def __init__(
        self, width: int, height: int, palette: list[int], base_code: int = 0x20
    ):
        self._size = (width, height)
        self._palette = bytes(palette)
        self._num_colors = max(2, len(palette) // 3)
        self._base_code = base_code
        self.ops: list[SpriteOp] = []

    def _next_code(self) -> int:
        return (self._base_code + len(self.ops)) & 0xFF

    @property
    def size(self) -> tuple[int, int]:
        return self._size

    def fill_rect(self, x: int, y: int, w: int, h: int, color_index: int) -> None:
        if w <= 0 or h <= 0:
            return
        self.ops.append(
            SpriteOp(
                w,
                h,
                self._num_colors,
                self._palette,
                bytes([color_index] * (w * h)),
                x,
                y,
                code=self._next_code(),
            )
        )

    def blit_coverage(
        self, coverage: Image.Image, x: int, y: int, palette_base: int, levels: int
    ) -> None:
        step = 255 / (levels - 1)
        idx = coverage.point(lambda p: palette_base + min(levels - 1, int(round(p / step))))
        self.ops.append(
            SpriteOp(
                coverage.width,
                coverage.height,
                self._num_colors,
                self._palette,
                bytes(idx.tobytes()),
                x,
                y,
                code=self._next_code(),
            )
        )

    def present(self) -> None:
        pass
