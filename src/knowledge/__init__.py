"""Engineering knowledge beyond individual parts: reusable design patterns (functional blocks).

Patterns sit between the curriculum (what to learn) and the component registry (what to buy):
they describe *how parts are combined* to perform a function, with ports that bind to the rest
of a design. They are used by the AI planner (as authoritative wiring knowledge), by the studio
(insert a block) and by explanations (what does this group of parts do).
"""
from .patterns import (DesignPattern, PatternFragment, PatternStore, apply_fragment, get_default_patterns,
                       instantiate_pattern)

__all__ = ["DesignPattern", "PatternFragment", "PatternStore", "apply_fragment", "get_default_patterns", "instantiate_pattern"]
