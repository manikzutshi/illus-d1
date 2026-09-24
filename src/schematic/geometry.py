"""Integer grid geometry for schematic symbols.

Coordinates are in *grid units* (gu); +x right, +y down (screen convention).
A symbol instance transform is: mirror (about the local y axis) → rotate clockwise
by 0/90/180/270 → translate. All pin tips of all symbols lie on integer grid points,
so every transformed pin tip is an integer point as well.
"""
from __future__ import annotations

from typing import Iterable, Literal, Tuple

Orientation = Literal["left", "right", "up", "down"]
Point = Tuple[int, int]

VEC: dict[str, Point] = {"left": (-1, 0), "right": (1, 0), "up": (0, -1), "down": (0, 1)}
OPPOSITE: dict[str, str] = {"left": "right", "right": "left", "up": "down", "down": "up"}
ROTATIONS = (0, 90, 180, 270)


def _rot(x: float, y: float, rotation: int) -> tuple[float, float]:
    r = rotation % 360
    if r == 0:
        return x, y
    if r == 90:       # clockwise on screen (y down)
        return -y, x
    if r == 180:
        return -x, -y
    if r == 270:
        return y, -x
    raise ValueError(f"rotation must be a multiple of 90, got {rotation}")


def transform_point(x: float, y: float, ox: float, oy: float, rotation: int = 0, mirror: bool = False) -> tuple[float, float]:
    if mirror:
        x = -x
    rx, ry = _rot(x, y, rotation)
    return rx + ox, ry + oy


def transform_ipoint(x: int, y: int, ox: int, oy: int, rotation: int = 0, mirror: bool = False) -> Point:
    rx, ry = transform_point(x, y, ox, oy, rotation, mirror)
    return int(round(rx)), int(round(ry))


def transform_orientation(orient: str, rotation: int = 0, mirror: bool = False) -> str:
    dx, dy = VEC[orient]
    tx, ty = transform_point(dx, dy, 0, 0, rotation, mirror)
    for name, v in VEC.items():
        if v == (int(round(tx)), int(round(ty))):
            return name
    raise AssertionError("unreachable")


def transform_bbox(b: tuple[float, float, float, float], ox: float, oy: float, rotation: int = 0, mirror: bool = False):
    x0, y0, x1, y1 = b
    pts = [transform_point(x, y, ox, oy, rotation, mirror) for x, y in ((x0, y0), (x1, y0), (x0, y1), (x1, y1))]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def bbox_union(boxes: Iterable[tuple[float, float, float, float]]):
    boxes = list(boxes)
    if not boxes:
        return (0.0, 0.0, 0.0, 0.0)
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def bbox_inflate(b, d: float):
    return (b[0] - d, b[1] - d, b[2] + d, b[3] + d)


def bbox_intersects(a, b) -> bool:
    """Strict overlap (touching edges do not count)."""
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def point_on_segment(p: Point, a: Point, b: Point) -> bool:
    """True if integer point p lies on the axis-aligned segment a–b (inclusive)."""
    (px, py), (ax, ay), (bx, by) = p, a, b
    if ax == bx == px:
        return min(ay, by) <= py <= max(ay, by)
    if ay == by == py:
        return min(ax, bx) <= px <= max(ax, bx)
    return False
