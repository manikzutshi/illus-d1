# ADR 005: Visual Asset Strategy

## Status
Accepted

## Context
Phase 4.2 requires a deterministic asset pipeline to replace placeholder cubes and generic geometries with recognizable components (ESP32, HC-SR04, LEDs) without downloading random internet models or injecting external logic. 

## Decision
We introduce an explicit `AssetRegistry` mapping component types to `AssetDefinition` metadata. 

Each component explicitly defines its:
1. `source`: Either `'procedural'` or `'glb'`.
2. `dimensions`: Known physical boundaries.
3. `anchorOffsets`: (Future integration) Exact millimeter offsets from component center if not computed dynamically via footprints.

For Phase 4.2, we prioritize **Enhanced Procedural Geometry** using `@react-three/fiber` primitives (Cylinders, Boxes, standard materials) over loading GLTF assets. This keeps the application perfectly self-contained, lightning fast, and avoids copyright/provenance issues with community models. 

When a component is not found in the asset registry, it falls back gracefully to an `'unknown'` block representation without crashing the renderer.

## Consequences
- **Positive**: No external dependencies or asynchronous model loading overhead.
- **Positive**: Strict separation of visual representations from electrical/logical metadata.
- **Negative**: Visuals remain stylized and educational rather than photorealistic CAD.
- **Negative**: Adds a layer of mapping maintenance inside `frontend/src/core/assets.ts`.

## Alternatives Considered
- **Prompting LLM for Three.js code**: Rejected. AI is strictly forbidden from writing or altering rendering coordinates to prevent hallucinated layouts.
- **Downloading community GLTF assets**: Rejected for Phase 4.2 to maintain self-contained predictability, though the schema (`source: 'glb'`) accommodates this in future phases.
