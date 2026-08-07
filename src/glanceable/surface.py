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
    """One TxSprite-shaped payload. Field names mirror brilliant_msg.TxSprite
    so this can be handed straight to it."""

    width: int
    height: int
    num_colors: int
    palette_data: bytes
    pixel_data: bytes
    x: int
    y: int


class SpriteSurface(Surface):
    """Accumulates ops as TxSprite-compatible payloads for the real device.

    NOTE: emitted against the published brilliant_msg 7.0.0 shapes but NOT yet
    validated on hardware. Treat the wire format as unconfirmed until it has
    been round-tripped on a physical Halo.
    """

    def __init__(self, width: int, height: int, palette: list[int]):
        self._size = (width, height)
        self._palette = bytes(palette)
        self._num_colors = max(2, len(palette) // 3)
        self.ops: list[SpriteOp] = []

    @property
    def size(self) -> tuple[int, int]:
        return self._size

    def fill_rect(self, x: int, y: int, w: int, h: int, color_index: int) -> None:
        if w <= 0 or h <= 0:
            return
        self.ops.append(
            SpriteOp(w, h, self._num_colors, self._palette, bytes([color_index] * (w * h)), x, y)
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
            )
        )

    def present(self) -> None:
        pass
