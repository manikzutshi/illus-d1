# ADR 001: Phase-1 Scope and Vertical Slice

## Context
The curriculum encompasses a massive 14-module VLSI backbone and a 40-domain knowledge architecture, ranging from simple embedded systems to complex semiconductor fabrication visualisations. Attempting to build the entire registry, simulation abstraction, and AI orchestration layer simultaneously poses a massive execution risk.

## Decision
For Phase 1, we will constrain the scope to **ONE complete vertical slice** to prove the architecture, rather than building the breadth of the semiconductor platform. 

The candidate golden project is **SMART PARKING**.

### The Vertical Slice Pipeline:
1. **Natural Language Input:** "Make a smart parking system using ESP32, ultrasonic sensor and LED"
2. **Clarification:** AI handles missing requirements.
3. **Component Resolution:** Maps to specific entries in the Component Registry.
4. **Design IR:** Generates the canonical JSON state.
5. **Deterministic Validation:** DRC/ERC checks.
6. **Simulation:** Preparation of simulation state (e.g., via Wokwi).
7. **Firmware:** Generation and compilation of C++ for the ESP32.
8. **Rendering:** 3D visualization of the breadboard state.
9. **Iterative Repair:** AI fixes validation or compilation errors based on deterministic feedback.

## Consequences
- We will purposefully ignore complex SPICE simulations, RTL/Verilog, and semiconductor physics visualizations in Phase 1.
- The Component Registry will be seeded with only the parts necessary for the Smart Parking project.
- This ensures the `AI -> Deterministic Validation -> Simulation -> Render` loop is robust before scaling the domain knowledge.
