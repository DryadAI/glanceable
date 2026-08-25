"""Damage tracking for surfaces that cannot afford a repaint.

Device-free by construction: this module knows about ``Surface`` ops and
rectangles, nothing else. It lives above ``surface.py`` and stays there.

Named ``damage`` rather than ``geometry`` because ``geometry.py`` is the chord
solver and these are different problems -- one is about the shape of the glass,
this is about what changed since the last frame.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Merge damage boxes within this many pixels. One background fill plus a few
#: redundant redraws beats two round trips.
DEFAULT_MERGE_GAP = 6

#: Above this many regions the per-region overhead has overtaken the saving.
DEFAULT_MAX_REGIONS = 6


@dataclass(frozen=True)
class Box:
    """Axis-aligned rectangle. ``x``/``y`` inclusive, ``w``/``h`` extents."""

    x: int
    y: int
    w: int
    h: int

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h

    @property
    def area(self) -> int:
        return max(0, self.w) * max(0, self.h)

    @property
    def is_empty(self) -> bool:
        return self.w <= 0 or self.h <= 0

    def intersects(self, other: "Box", gap: int = 0) -> bool:
        if self.is_empty or other.is_empty:
            return False
        return (
            self.x - gap < other.right
            and other.x - gap < self.right
            and self.y - gap < other.bottom
            and other.y - gap < self.bottom
        )

    def union(self, other: "Box") -> "Box":
        if self.is_empty:
            return other
        if other.is_empty:
            return self
        x, y = min(self.x, other.x), min(self.y, other.y)
        return Box(x, y, max(self.right, other.right) - x, max(self.bottom, other.bottom) - y)

    def clip(self, bounds: "Box") -> "Box":
        x, y = max(self.x, bounds.x), max(self.y, bounds.y)
        return Box(x, y, min(self.right, bounds.right) - x, min(self.bottom, bounds.bottom) - y)


EMPTY = Box(0, 0, 0, 0)


class Op:
    """One recorded ``Surface`` call."""

    def box(self) -> Box:  # pragma: no cover - interface
        raise NotImplementedError

    def replay(self, surface) -> None:  # pragma: no cover - interface
        raise NotImplementedError


@dataclass(frozen=True)
class FillRect(Op):
    x: int
    y: int
    w: int
    h: int
    color_index: int

    def box(self) -> Box:
        return Box(self.x, self.y, self.w, self.h)

    def replay(self, surface) -> None:
        surface.fill_rect(self.x, self.y, self.w, self.h, self.color_index)


@dataclass(frozen=True)
class BlitCoverage(Op):
    """A coverage blit.

    Equality is by ``digest`` -- the coverage bytes -- so an identical run
    re-rendered at the same place compares equal and produces no damage. The
    image itself is excluded from comparison but carried for replay.
    """

    x: int
    y: int
    w: int
    h: int
    palette_base: int
    levels: int
    digest: bytes
    image: object = field(compare=False, repr=False, default=None)

    def box(self) -> Box:
        return Box(self.x, self.y, self.w, self.h)

    def replay(self, surface) -> None:
        surface.blit_coverage(self.image, self.x, self.y, self.palette_base, self.levels)


@dataclass(frozen=True)
class Region:
    """A rectangle to repaint, and the ops inside it in draw order.

    ``needs_fill`` is False for a pure addition onto known background -- the
    fill would be a wasted write.
    """

    box: Box
    ops: tuple[Op, ...]
    needs_fill: bool = True


@dataclass(frozen=True)
class DamagePlan:
    regions: tuple[Region, ...] = ()
    first_paint: bool = False

    @property
    def is_empty(self) -> bool:
        return not self.regions

    @property
    def area(self) -> int:
        return sum(r.box.area for r in self.regions)


def merge_boxes(boxes, gap: int = DEFAULT_MERGE_GAP) -> list[Box]:
    """Transitively merge overlapping or near-adjacent boxes to a fixpoint."""
    pending = [b for b in boxes if not b.is_empty]
    merged: list[Box] = []
    while pending:
        current = pending.pop()
        absorbed = True
        while absorbed:
            absorbed = False
            rest = []
            for other in pending:
                if current.intersects(other, gap=gap):
                    current = current.union(other)
                    absorbed = True
                else:
                    rest.append(other)
            pending = rest
        merged.append(current)
    merged.sort(key=lambda b: (b.y, b.x))
    return merged


def plan(
    previous: tuple[Op, ...] | None,
    current: tuple[Op, ...],
    bounds: Box,
    *,
    merge_gap: int = DEFAULT_MERGE_GAP,
    max_regions: int = DEFAULT_MAX_REGIONS,
) -> DamagePlan:
    """Minimal repaint turning ``previous`` into ``current``.

    ``previous`` of ``None`` means the panel contents are unknown, so all of
    ``bounds`` is damaged.
    """
    if previous is None:
        keep = tuple(op for op in current if op.box().clip(bounds).area > 0)
        return DamagePlan(regions=(Region(bounds, keep),), first_paint=True)

    if previous == current:
        return DamagePlan()

    from collections import Counter

    old, new = Counter(previous), Counter(current)
    removed, added = old - new, new - old

    # Removed ops leave pixels behind and must be filled. Added ops only need a
    # fill where the previous frame actually put something.
    fill = [op.box() for op in removed.elements()]
    additive = []
    old_boxes = [op.box() for op in previous]
    for op in added.elements():
        box = op.box()
        (fill if any(box.intersects(b) for b in old_boxes) else additive).append(box)

    fill = [b.clip(bounds) for b in fill]
    additive = [b.clip(bounds) for b in additive]
    boxes = merge_boxes(fill + additive, gap=merge_gap)

    if len(boxes) > max_regions:
        merged = EMPTY
        for b in boxes:
            merged = merged.union(b)
        boxes = [merged]

    if not boxes:
        return DamagePlan()

    return DamagePlan(
        regions=tuple(
            Region(
                box,
                tuple(op for op in current if op.box().intersects(box)),
                needs_fill=any(d.intersects(box) for d in fill),
            )
            for box in boxes
        )
    )
