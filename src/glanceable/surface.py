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
class SpritePayload:
    """The pixels. Field-for-field brilliant_msg.TxSprite, so

        TxSprite(**dataclasses.asdict(payload))

    constructs without translation. Carries no position: TxSprite has none.
    """

    width: int
    height: int
    num_colors: int
    palette_data: bytes
    pixel_data: bytes
    compress: bool = False


@dataclass
class SpriteCoords:
    """The placement. Field-for-field brilliant_msg.TxSpriteCoords.

    `code` binds this to its payload; it is an unsigned byte. `offset` is a
    palette offset in 0..15.

    x/y are emitted **1-based**. Halo's display primitives all do
    `if (v < 1) v = 1; v -= 1;`, so a 0-based origin lands every sprite one
    pixel up and left. The conversion from this library's 0-based geometry
    happens in SpriteSurface._emit, at the wire and nowhere above it.

    Confirmed by round-tripping these bytes through brilliant_msg 7.1.1 and
    halo-emulator. Not yet seen on physical glass.
    """

    code: int
    x: int
    y: int
    offset: int = 0


@dataclass
class SpriteOp:
    """One accumulated draw, which is *two* messages on the wire.

    brilliant_msg 7.0.0 splits pixels from placement: TxSprite has no x/y, and
    TxSpriteCoords positions it by `code`. Emitting a single flat struct was
    wrong -- splatting it into TxSprite raised TypeError on `x`.

    Deliberately imports nothing from brilliant_msg. Keeping the device SDK out
    of the library is exactly what rule 1 in CLAUDE.md protects: the moment
    this module imports a vendor package, PILSurface and SpriteSurface stop
    being interchangeable and the boundary rots.
    """

    payload: SpritePayload
    coords: SpriteCoords

    # Passthroughs. The op log has to stay comparable against PILSurface's
    # (x, y, w, h) tuples or the surface-agreement test loses its teeth.
    @property
    def x(self) -> int:
        return self.coords.x

    @property
    def y(self) -> int:
        return self.coords.y

    @property
    def width(self) -> int:
        return self.payload.width

    @property
    def height(self) -> int:
        return self.payload.height

    @property
    def code(self) -> int:
        return self.coords.code


class SpriteSurface(Surface):
    """Accumulates ops as TxSprite/TxSpriteCoords payloads for the real device.

    Each op becomes two messages on the wire. `base_code` seeds the per-sprite
    identifier that binds a pixel payload to its placement; codes are unsigned
    bytes, so they wrap at 256. Which codes are safe to use is the application's
    business -- the SDK does not reserve a range.

    Field shapes are verified field-for-field against brilliant_msg 7.1.1:
    SpritePayload matches TxSprite (width, height, num_colors, palette_data,
    pixel_data, compress) and SpriteCoords matches TxSpriteCoords (code, x, y,
    offset), both in declaration order, so asdict() splats cleanly. msg_code is
    applied by BrilliantMsg.send_message() at send time and correctly absent
    from both.

    Halo is supported: brilliant_msg ships device-side sprite.lua whose
    set_palette() branches on frame.HARDWARE_VERSION, using integer palette
    indices 0-15 on Halo against colour names on Frame, then renders through
    frame.display.bitmap.

    Pixels stay one byte per pixel here. TxSprite.pack() does the bit packing
    (_pack_1bit/_pack_2bit/_pack_4bit); pre-packing would double-encode.

    Coordinates go out 1-based, because frame.display.bitmap is 1-based on
    Halo and clamps anything below 1 up to 1 before subtracting. See _emit.

    palette_base is not supported here and raises; see blit_coverage for why
    the device has no equivalent of it.
    """

    def __init__(
        self, width: int, height: int, palette: list[int], base_code: int = 0x20
    ):
        self._size = (width, height)

        # TxSprite.pack() buckets bpp by num_colors (<=2 -> 1bpp, <=4 -> 2bpp,
        # else 4bpp) and the device-side sprite.lua slices the palette as
        # exactly num_colors*3 bytes, treating everything after as pixel data.
        # An unrounded count would desynchronise that slice.
        supplied = max(2, len(palette) // 3)
        self._num_colors = 2 if supplied <= 2 else 4 if supplied <= 4 else 16
        if supplied > 16:
            raise ValueError(
                f"palette holds {supplied} colours; the sprite format caps at 16"
            )

        # Truncate to the declared count. sprite.lua reads the palette as
        # string.sub(data, 8, 8 + num_colors*3 - 1) and takes the remainder as
        # pixels, so a longer palette shifts every pixel and corrupts the frame.
        # brilliant_msg's own from_indexed_png_bytes truncates the same way.
        self._palette = bytes(palette[: self._num_colors * 3]).ljust(
            self._num_colors * 3, b"\x00"
        )

        self._base_code = base_code
        self._code_seq = 0
        self.ops: list[SpriteOp] = []

    def _next_code(self) -> int:
        """Per-sprite identifier, cycling within the byte range above base.

        Previously derived from len(self.ops), which never resets because
        present() does not clear the log -- so codes wrapped past 0xFF and
        collided with sprites still live on the device.
        """
        span = 0x100 - self._base_code
        code = self._base_code + (self._code_seq % span)
        self._code_seq += 1
        return code

    def reset_codes(self) -> None:
        """Restart code allocation. Call when the device display is cleared."""
        self._code_seq = 0

    def _emit(self, w: int, h: int, pixels: bytes, x: int, y: int) -> None:
        self.ops.append(
            SpriteOp(
                payload=SpritePayload(
                    width=w,
                    height=h,
                    num_colors=self._num_colors,
                    palette_data=self._palette,
                    pixel_data=pixels,
                ),
                # +1: every Halo display primitive is 1-based and does
                # `if (v < 1) v = 1; v -= 1;` internally, so passing this
                # library's 0-based geometry straight through lands each
                # sprite one pixel up and left -- and silently clamps, rather
                # than shifts, anything at the very top or left edge. The
                # conversion belongs here, at the wire, so nothing above
                # surface.py has to know the device counts from one.
                coords=SpriteCoords(code=self._next_code(), x=x + 1, y=y + 1),
            )
        )

    def messages(self) -> list[tuple[SpritePayload, SpriteCoords]]:
        """The frame as (pixels, placement) pairs, in draw order.

        Send each pair as two messages; the payload must reach the device
        before the coords that position it.
        """
        return [(op.payload, op.coords) for op in self.ops]

    @property
    def size(self) -> tuple[int, int]:
        return self._size

    def fill_rect(self, x: int, y: int, w: int, h: int, color_index: int) -> None:
        if w <= 0 or h <= 0:
            return
        self._emit(w, h, bytes([color_index] * (w * h)), x, y)

    def blit_coverage(
        self, coverage: Image.Image, x: int, y: int, palette_base: int, levels: int
    ) -> None:
        # A non-zero palette_base cannot survive the wire, and fails silently
        # if allowed through. TxSprite.pack() masks every index down to the
        # declared bit depth, so at levels=4 (2bpp) base=4 emits index 7 and
        # base=12 emits 15, and both arrive as 3: every base produces byte-
        # identical output. PILSurface honours the base, so the two backends
        # would diverge with the host suite still green -- the exact failure
        # shape rule 1 exists to catch.
        #
        # The device mechanism for shifting a sprite's colours is bitmap()'s
        # palette_offset, carried on SpriteCoords.offset. But it is not a
        # substitute: sprite.lua's set_palette() always assigns firmware
        # entries starting at index 0, so an offset on its own just points at
        # slots nothing has written. Wiring it up means changing what the
        # device-side Lua loads, not what this method emits.
        if palette_base != 0:
            raise ValueError(
                f"SpriteSurface cannot express palette_base={palette_base}: "
                "TxSprite.pack() masks indices to the declared bit depth, so "
                "every palette_base sends identical bytes. Use palette_base=0 "
                "and place the ramp at the bottom of the palette."
            )
        step = 255 / (levels - 1)
        idx = coverage.point(lambda p: min(levels - 1, int(round(p / step))))
        self._emit(coverage.width, coverage.height, bytes(idx.tobytes()), x, y)

    def present(self) -> None:
        pass

