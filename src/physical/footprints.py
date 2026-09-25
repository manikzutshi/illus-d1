"""Physical definitions: how a registry component type becomes something that can be placed.

Resolution (first match wins, fields merge in this order):
  1. idealised primitives (object_type != PHYSICAL) and `mounting: virtual`  -> no physical form
  2. package template  data/physical/packages.yaml, keyed by `physical.package`
  3. per-part entry    data/physical/parts.yaml, keyed by component_type_id (overrides the template)
  4. honest fallback   an off-board "generic module" with a header in registry pin order,
                       geometry source "assumed", flagged in physical verification

Nothing here is part-specific code: all part knowledge lives in the two YAML files.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

from core.enums import ObjectType
from core.models import ComponentType

from .breadboard import PITCH_MM

_DATA = Path(__file__).resolve().parent.parent.parent / "data" / "physical"

SOURCE_RANK = {"datasheet": 0, "standard": 1, "typical": 2, "assumed": 3}


@dataclass
class Terminal:
    """A connection point of an off-board item, relative to its body centre (z from the table)."""
    pin_id: str
    style: str                      # lead | header | screw | pad
    at: Tuple[float, float, float]
    color: Optional[str] = None


@dataclass
class Footprint:
    component_type_id: str
    mount: str                      # breadboard | offboard | virtual
    template: str                   # two_lead | inline | dip | dual_row | smd_adapter | offboard | virtual
    pins: List[str] = field(default_factory=list)                    # site order (inline / two_lead)
    numbers: Dict[str, int] = field(default_factory=dict)            # dip / dual_row pin numbers
    total_pins: int = 0
    spans: List[int] = field(default_factory=list)
    pitch_steps: int = 1
    row_span: int = 3
    body_mm: Tuple[float, float, float] = (5.0, 5.0, 5.0)
    body_z: float = 0.5
    body_offset_mm: Optional[Tuple[float, float]] = None
    visual: str = "generic_module"
    source: str = "assumed"
    notes: List[str] = field(default_factory=list)
    variant_note: Optional[str] = None
    terminals: List[Terminal] = field(default_factory=list)
    internal_links: List[List[str]] = field(default_factory=list)
    pin_alias: Dict[str, str] = field(default_factory=dict)
    unmapped: List[str] = field(default_factory=list)                 # engineering pins without a physical site
    fallback: bool = False
    asset_url: Optional[str] = None
    _sites_cache: Dict[Optional[int], List[Tuple[str, float, float]]] = field(default_factory=dict, repr=False, compare=False)

    # ── grid sites (unrotated, pitch units, first pin at the origin) ─────────
    def sites(self, span: Optional[int] = None) -> List[Tuple[str, float, float]]:
        cached = self._sites_cache.get(span)
        if cached is None:
            cached = self._sites_cache[span] = self._compute_sites(span)
        return cached

    def _compute_sites(self, span: Optional[int]) -> List[Tuple[str, float, float]]:
        if self.template == "two_lead":
            s = span if span is not None else (self.spans[0] if self.spans else 1)
            return [(self.pins[0], 0.0, 0.0), (self.pins[1], float(s), 0.0)]
        if self.template in ("inline", "smd_adapter"):
            return [(p, float(i * self.pitch_steps), 0.0) for i, p in enumerate(self.pins)]
        if self.template in ("dip", "dual_row"):
            n = self.total_pins
            half = n // 2
            out = []
            for pin, k in sorted(self.numbers.items(), key=lambda t: t[1]):
                if k <= half:
                    out.append((pin, float(self.pitch_steps * (k - 1)), 0.0))
                else:
                    out.append((pin, float(self.pitch_steps * (n - k)), float(self.row_span)))
            return out
        return []

    def extent_steps(self) -> int:
        """Columns spanned along the row direction (unrotated), for board-size estimates."""
        if self.template == "two_lead":
            return (self.spans[0] if self.spans else 1) + 1
        if self.template in ("dip", "dual_row"):
            return self.pitch_steps * (self.total_pins // 2 - 1) + 1
        if self.template in ("inline", "smd_adapter"):
            return self.pitch_steps * (len(self.pins) - 1) + 1
        return 0

    def body_center_mm(self, sites: List[Tuple[str, float, float]]) -> Tuple[float, float]:
        if self.body_offset_mm is not None:
            return self.body_offset_mm
        if not sites:
            return (0.0, 0.0)
        xs = [s[1] for s in sites]
        ys = [s[2] for s in sites]
        return ((min(xs) + max(xs)) / 2 * PITCH_MM, (min(ys) + max(ys)) / 2 * PITCH_MM)


@lru_cache(maxsize=1)
def _data() -> Tuple[dict, dict]:
    pk = yaml.safe_load((_DATA / "packages.yaml").read_text(encoding="utf-8")) or {}
    pt = yaml.safe_load((_DATA / "parts.yaml").read_text(encoding="utf-8")) or {}
    return pk.get("packages", {}) or {}, pt.get("parts", {}) or {}


def _numbered(ctype: ComponentType) -> Dict[str, int]:
    out = {}
    for p in ctype.pins:
        if p.number and str(p.number).isdigit():
            out[p.pin_id] = int(p.number)
    return out


def _header_terminals(spec: dict, default_style: str = "header") -> List[Terminal]:
    pins = spec.get("pins", [])
    pitch = float(spec.get("pitch", PITCH_MM))
    x0 = spec.get("x0", -pitch * (len(pins) - 1) / 2)
    return [Terminal(p, spec.get("style", default_style), (x0 + i * pitch, float(spec.get("y", 0.0)), float(spec.get("z", 3.0))))
            for i, p in enumerate(pins)]


def resolve_footprint(ctype: Optional[ComponentType]) -> Footprint:
    if ctype is None:
        return Footprint("unknown", "virtual", "virtual", source="assumed", notes=["Unknown component type"])
    cid = ctype.component_type_id
    phys = ctype.physical
    if ctype.object_type != ObjectType.PHYSICAL or (phys is not None and phys.mounting == "virtual"):
        return Footprint(cid, "virtual", "virtual", source="standard",
                         notes=["Idealised primitive: it has no physical form."])

    packages, parts = _data()
    entry = dict(parts.get(cid, {}))
    pkg_key = entry.get("package") or (phys.package if phys else None)
    raw: dict = dict(packages.get(pkg_key, {})) if pkg_key else {}
    raw.update(entry)
    template = raw.get("template")
    registry_order = [p.pin_id for p in ctype.pins]

    if template is None:
        return _fallback(ctype, pkg_key)

    fp = Footprint(cid, "offboard" if template == "offboard" else "breadboard", template)
    fp.source = raw.get("source", "typical")
    fp.visual = raw.get("visual", {"dip": "dip", "inline": "header", "two_lead": "radial",
                                   "smd_adapter": "smd_adapter", "offboard": "generic_module",
                                   "dual_row": "module_pcb"}.get(template, "generic_module"))
    fp.body_mm = tuple(raw.get("body_mm", fp.body_mm))
    fp.body_z = float(raw.get("body_z", fp.body_z))
    if raw.get("body_offset_mm") is not None:
        fp.body_offset_mm = tuple(raw["body_offset_mm"])
    fp.spans = [int(s) for s in raw.get("spans", [])]
    fp.pitch_steps = int(raw.get("pitch_steps", 1))
    fp.row_span = int(raw.get("row_span", 3))
    fp.internal_links = [list(g) for g in raw.get("internal_links", [])]
    fp.pin_alias = dict(raw.get("pin_alias", {}))
    fp.variant_note = raw.get("variant_note")
    fp.asset_url = (phys.asset_3d if phys else None) or ctype.asset_3d or raw.get("asset_3d")
    for key in ("note",):
        if raw.get(key):
            fp.notes.append(raw[key])

    if template in ("two_lead", "inline", "smd_adapter"):
        order = raw.get("pin_order")
        if not order:
            nums = _numbered(ctype)
            if nums and len(nums) == len(registry_order):
                order = [p for p, _ in sorted(nums.items(), key=lambda t: t[1])]
            else:
                order = registry_order
                fp.source = "assumed"
                fp.variant_note = fp.variant_note or "Pin order is not recorded in the library; shown in registry order."
        fp.pins = [p for p in order if p in registry_order]
        fp.unmapped = [p for p in registry_order if p not in fp.pins and p not in fp.pin_alias]
        if template == "two_lead" and len(fp.pins) != 2:
            return _fallback(ctype, pkg_key)
        if template == "smd_adapter":
            # a SIP breakout: a small PCB standing upright along its pin row, the chip on its face
            fp.body_mm = (max(2.54 * len(fp.pins) + 1.0, 6.0), 1.6, 12.0)
            fp.body_z = 2.5
            fp.body_offset_mm = None
    elif template in ("dip", "dual_row"):
        nums = raw.get("pin_numbers") or _numbered(ctype)
        fp.numbers = {p: int(n) for p, n in nums.items() if p in registry_order}
        fp.total_pins = int(raw.get("pins") or raw.get("total_pins") or (max(fp.numbers.values()) if fp.numbers else 0))
        if fp.total_pins % 2:
            fp.total_pins += 1
        fp.unmapped = [p for p in registry_order if p not in fp.numbers and p not in fp.pin_alias]
        if not fp.numbers:
            return _fallback(ctype, pkg_key)
    elif template == "offboard":
        terms: List[Terminal] = []
        for t in raw.get("terminals", []) or []:
            terms.append(Terminal(t["pin"], t.get("style", "header"), tuple(t["at"]), t.get("color")))
        for key in ("header", "header2"):
            if raw.get(key):
                terms.extend(_header_terminals(raw[key]))
        if not terms:
            terms = _header_terminals({"pins": registry_order, "y": fp.body_mm[1] / 2 - 2.0, "z": 3.0})
            fp.source = "assumed"
        fp.terminals = [t for t in terms if t.pin_id in registry_order]
        mapped = {t.pin_id for t in fp.terminals}
        fp.unmapped = [p for p in registry_order if p not in mapped and p not in fp.pin_alias]
    return fp


def _fallback(ctype: ComponentType, pkg_key: Optional[str]) -> Footprint:
    """Off-board labelled module with one header in registry order. Never pretends to be accurate."""
    pins = [p.pin_id for p in ctype.pins]
    n = max(len(pins), 1)
    length = max(2.54 * n + 6.0, 16.0)
    fp = Footprint(ctype.component_type_id, "offboard", "offboard", pins=pins,
                   body_mm=(length, 16.0, 6.0), body_z=0.0, visual="generic_module", source="assumed",
                   fallback=True)
    fp.terminals = _header_terminals({"pins": pins, "y": 6.0, "z": 3.0})
    why = f"package '{pkg_key}' has no geometry template" if pkg_key else "no physical data in the library"
    fp.notes.append(f"Shown as a generic module: {why}. Pin positions follow the registry order and are not real.")
    return fp


def footprint_sources() -> Dict[str, str]:
    """For reporting: which component ids have an explicit per-part entry."""
    return {k: v.get("source", "") for k, v in _data()[1].items()}
