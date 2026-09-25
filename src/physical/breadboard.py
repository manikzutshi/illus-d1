"""Solderless breadboard model: geometry, hole names and electrical connectivity.

Board frame (millimetres): x runs along the columns (column 1 on the left), y runs across the
rows (row a at the top, row j at the bottom, the centre trench at y = 0), z is up with the top
surface at z = 0. Positions are kept in "pitch units" (1 pu = 2.54 mm) internally so every hole
sits on an exact grid.

Connectivity (standard solderless breadboard):
  * terminal strips: rows a-e of one column are connected ("top:<col>"), rows f-j likewise
    ("bot:<col>"); the trench separates them;
  * power rails: each of the four rails is one connected node ("rail:T+", ...). Rails are modelled
    as continuous along the board; some full-size boards split them in the middle - that is not
    modelled.
Rail holes are arranged in groups of five with a one-hole gap, as printed on common boards.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, List, Literal, Optional, Tuple

PITCH_MM = 2.54
TERMINAL_ROWS = "abcdefghij"
# Row centre lines in pitch units (the trench is 3 pitches wide between e and f, so a DIP's pin rows
# are 7.62 mm apart).
ROW_YP: Dict[str, float] = {"a": -5.5, "b": -4.5, "c": -3.5, "d": -2.5, "e": -1.5,
                            "f": 1.5, "g": 2.5, "h": 3.5, "i": 4.5, "j": 5.5}
# Rails: inner rows are "+" (red line), outer rows "-" (blue line), on both sides. Printed polarity
# differs between manufacturers; the labels only matter for how the board is drawn.
RAIL_YP: Dict[str, float] = {"T-": -9.5, "T+": -8.5, "B+": 8.5, "B-": 9.5}
RAIL_POLARITY: Dict[str, str] = {"T+": "+", "T-": "-", "B+": "+", "B-": "-"}
BoardKind = Literal["half", "full"]


@dataclass(frozen=True)
class BoardSpec:
    kind: str
    name: str
    columns: int
    rail_first_column: int
    rail_groups: int
    size_mm: Tuple[float, float, float]        # length (x), width (y), height (z)
    note: str = ""


BOARD_SPECS: Dict[str, BoardSpec] = {
    # 400 tie points: 30 x 10 terminal holes + 4 rails x 25 holes. Typical outline 82.5 x 54.5 x 8.5 mm.
    "half": BoardSpec("half", "Half-size breadboard (400 tie points)", 30, 1, 5, (82.5, 57.4, 8.5),
                      "Outline width follows the modelled rail spacing (real boards: ~54.5 mm)."),
    # 830 tie points: 63 x 10 terminal holes + 4 rails x 50 holes. Typical outline 165 x 54.5 x 8.5 mm.
    "full": BoardSpec("full", "Full-size breadboard (830 tie points)", 63, 2, 10, (165.1, 57.4, 8.5),
                      "Rails modelled as continuous; some full-size boards split them in the middle."),
}


@dataclass
class Hole:
    hole_id: str               # "e12" (terminal) or "T+7" (rail hole under column 7)
    column: int
    row: str                   # terminal row letter or rail id
    xp: float                  # pitch units
    yp: float
    node: str                  # connected group: "top:12", "bot:12", "rail:T+"

    @property
    def x(self) -> float:
        return round(self.xp * PITCH_MM, 4)

    @property
    def y(self) -> float:
        return round(self.yp * PITCH_MM, 4)


@dataclass
class Breadboard:
    spec: BoardSpec
    holes: Dict[str, Hole] = field(default_factory=dict)
    by_grid: Dict[Tuple[int, float], str] = field(default_factory=dict)     # (column, yp) -> hole id
    node_holes: Dict[str, List[str]] = field(default_factory=dict)

    @property
    def columns(self) -> int:
        return self.spec.columns

    def column_xp(self, column: int) -> float:
        return column - (self.spec.columns + 1) / 2.0

    def hole_at(self, column: int, yp: float) -> Optional[Hole]:
        hid = self.by_grid.get((column, yp))
        return self.holes.get(hid) if hid else None

    def node_of(self, hole_id: str) -> Optional[str]:
        h = self.holes.get(hole_id)
        return h.node if h else None

    def rail_columns(self) -> List[int]:
        s = self.spec
        return [s.rail_first_column + g * 6 + k for g in range(s.rail_groups) for k in range(5)]

    def bounds_mm(self) -> Tuple[float, float, float, float]:
        L, W, _ = self.spec.size_mm
        return (-L / 2, -W / 2, L / 2, W / 2)

    @staticmethod
    def half_of(row: str) -> str:
        return "top" if row in "abcde" else "bot"


@lru_cache(maxsize=4)
def make_breadboard(kind: str = "half") -> Breadboard:
    spec = BOARD_SPECS[kind]
    bb = Breadboard(spec)
    for col in range(1, spec.columns + 1):
        xp = bb.column_xp(col)
        for row in TERMINAL_ROWS:
            hid = f"{row}{col}"
            node = f"{Breadboard.half_of(row)}:{col}"
            bb.holes[hid] = Hole(hid, col, row, xp, ROW_YP[row], node)
    for col in bb.rail_columns():
        xp = bb.column_xp(col)
        for rail, yp in RAIL_YP.items():
            hid = f"{rail}{col}"
            bb.holes[hid] = Hole(hid, col, rail, xp, yp, f"rail:{rail}")
    for hid, h in bb.holes.items():
        bb.by_grid[(h.column, h.yp)] = hid
        bb.node_holes.setdefault(h.node, []).append(hid)
    return bb


def yp_row(yp: float) -> Optional[str]:
    """Terminal row letter or rail id at a y position (pitch units), if any."""
    for r, v in ROW_YP.items():
        if v == yp:
            return r
    for r, v in RAIL_YP.items():
        if v == yp:
            return r
    return None


def parse_hole(hole_id: str) -> Tuple[str, int]:
    """'e12' -> ('e', 12); 'T+7' -> ('T+', 7)."""
    if hole_id[:2] in RAIL_YP:
        return hole_id[:2], int(hole_id[2:])
    return hole_id[0], int(hole_id[1:])
