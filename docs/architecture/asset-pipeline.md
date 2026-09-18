# Asset Pipeline Architecture

The illustration engine relies on a strictly separated rendering pipeline to convert logical `DesignProject` connections into physical, 3D representations.

## Asset Registry
The `ASSET_REGISTRY` (located in `frontend/src/core/assets.ts`) maps semantic component types to visual `AssetDefinition`s. 

An `AssetDefinition` contains:
- `component_type`: The electrical registry identifier (e.g., `sensor:hc-sr04`).
- `visual_type`: The visual identifier linking it to a specific rendering geometry logic (e.g., `hcsr04`).
- `source`: Declares whether the renderer should expect `'procedural'` runtime geometry or load a `'glb'` file.
- `dimensions`: Basic physical bounding boxes.

## Render Flow
1. The **PhysicalLayoutEngine** calculates physical bounding and routing anchors on the breadboard.
2. The **SceneBuilder** generates the `SceneGraph`, fetching the correct `AssetDefinition` for every logical component.
3. The **Scene3D** (React Three Fiber) ingests the `SceneGraph` nodes. 
4. Based on the `visual_type`, it renders either composed multi-mesh primitive objects (for procedural) or `<primitive>` GLB loads.

## Wire Routing Geometry
The pipeline converts logical net connections into curved physical wire assets:
1. `PhysicalLayoutEngine` outputs a polyline of 3D spatial points routing orthogonal Manhattan steps away from the breadboard.
2. `Scene3D` leverages `THREE.CatmullRomCurve3` to interpolate these sharp physical vectors into a smooth, recognizable jumper wire curve.
3. This curve is extruded into a `THREE.TubeGeometry` for convincing physical depth.

## Asset Fallbacks
To guarantee deterministic execution and avoid crashing on hallucinated or unknown AI components:
- The registry explicitly returns a fallback `visual_type: 'unknown'` object when lookup fails.
- The renderer explicitly matches `'unknown'` to a generic, labeled gray box.
