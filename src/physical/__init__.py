"""Physical projection of engineering designs: breadboard build, 3D scene data, physical verification."""
from .breadboard import BOARD_SPECS, make_breadboard
from .engine import generate_physical, placements_from_physical
from .footprints import Footprint, resolve_footprint
from .models import (PhysicalLayoutState, PhysicalPart, PhysicalPlacement, PhysicalProject, PhysicalVerification,
                     PhysicalWire)
from .verify import physical_connectivity, verify_physical

__all__ = [
    "BOARD_SPECS", "make_breadboard", "generate_physical", "placements_from_physical", "Footprint",
    "resolve_footprint", "PhysicalLayoutState", "PhysicalPart", "PhysicalPlacement", "PhysicalProject",
    "PhysicalVerification", "PhysicalWire", "physical_connectivity", "verify_physical",
]
