# Physical Layout Architecture

## Overview
Phase 4.1 introduces the `PhysicalLayoutEngine` to transition from an abstract logical scene into a physically constrained workspace (the breadboard). This engine deterministically maps the semantic connections of a `DesignProject` into physical 3D world coordinates before they are given to the renderer.

## BreadboardModel
The core coordinate authority is the `BreadboardModel`. It defines the physical constraints of a 400-point (half-size) breadboard:
- 30 columns, spaced by a `pitch` of 1.0 units (representing 2.54mm or 0.1").
- Rows A-E and F-J separated by a central trench.
- Top and bottom power/ground rails.
- Methods like `holeToWorld(col, row)` provide exact vector coordinates for placement.

## Component Footprints
Components possess physical constraints defined in the layout engine's footprint dictionary:
- `cols`: How many holes a component spans (e.g., the ESP32 spans 15 columns, an inline sensor spans 4).
- `rowSpan`: How many rows a component spans across the trench.
- `anchorMap`: A mapping from a semantic `pin_id` to a specific index on the footprint, resolving to a specific physical hole.

## Placement Algorithm
The `PhysicalLayoutEngine` employs a deterministic, rule-based algorithm prioritizing physical coherence:
1. **Controller (ESP32)**: Placed anchoring on the left side of the board across the trench.
2. **Primary Sensor (HC-SR04)**: Placed linearly on the right side of the board along a single row.
3. **Signal Modifiers (Voltage Divider)**: Resistors are laid out orthogonally spanning rows near the sensor nets (e.g. ECHO).
4. **Outputs (LED)**: The LED and its series resistor are placed alongside the primary controller's GPIO area.
5. **Fallbacks**: Any unidentified components are placed iteratively in remaining outer columns.

## Wire Routing
Instead of direct point-to-point floating connections, the engine uses a constrained Manhattan polyline system:
- Connections ascend strictly vertically from their actual pin insertion hole.
- Routing traverses horizontally to match the destination Z-axis.
- Routing traverses longitudinally to match the X-axis.
- Waypoint heights are incremented deterministically (`wireHeightOffset`) to prevent severe Z-fighting of concurrent nets.

## Relationship to SceneGraph
The `PhysicalLayoutEngine` feeds directly into the `SceneBuilder`. The `SceneNode` schema has been extended to include `world_anchors`—the absolute position of a specific pin hole in space. The 3D and 2D renderers simply paint meshes/lines against these deterministic coordinates, completely decoupling layout math from React component logic.
