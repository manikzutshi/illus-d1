# ADR 004: Rendering Stack

## Status
Accepted

## Context
Phase 4 requires a visible interface to display the `DesignProject` JSON in both 2D and 3D formats. The stack must be lightweight, capable of running entirely offline, and deterministic. It must not require a heavy full-stack web framework that invents its own engineering rules.

## Decision
We will use **Vite + React + TypeScript** for the web application, supplemented by **Three.js** and **React Three Fiber (@react-three/fiber)** for the 3D scene representation. The 2D schematic will utilize a native HTML5 **Canvas 2D** API.

The Python backend CLI (`illustration-engine render web <path>`) will export the target `DesignProject` JSON directly into the frontend's static `public` directory, and launch the Vite development server. 

## Consequences
- **Positive**: React Three Fiber makes it exceptionally easy to map our intermediate `SceneGraph` nodes directly to reactive 3D meshes.
- **Positive**: High separation of concerns. The backend retains absolute authority over the `DesignProject`.
- **Negative**: Adds a Node.js dependency layer for frontend building.
- **Negative**: We must maintain a duplicate partial schema for `DesignProject` in TypeScript (`types.ts`).

## Alternatives Considered
- *Python-based UI (Tkinter / PyQt)*: Rejected due to poor 3D capabilities and lack of web portability.
- *Unity / Unreal Engine*: Rejected as massive overkill for procedural breadboard logic.
- *Vanilla JS / WebGL*: Rejected due to high boilerplate overhead for managing 3D object picking and scene graphs.
