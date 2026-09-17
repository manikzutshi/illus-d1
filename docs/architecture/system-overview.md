# System Overview

## Problem Statement
We are building Phase 1 of a curriculum-grounded Generative Illustration / Engineering Visualization Engine for an educational semiconductor/VLSI platform. Students need to interact with an AI to design, visualize, simulate, and debug engineering systems (e.g., electronic circuits, digital logic). Current LLMs alone are prone to hallucination and cannot serve as the source of engineering truth. 

## Product Boundary
The system acts as an interactive learning and engineering visualization tool, rather than an unrestricted text-to-image generator or a purely conversational AI. It is strictly bounded by a curriculum and a domain knowledge architecture, ensuring all generated artifacts map to valid engineering concepts, simulations, and visualizations. 

## Architectural Philosophy
1. **AI Proposes, Determinism Disposes:** The LLM acts as an orchestrator proposing solutions. Deterministic software validates, calculates, simulates, and renders. The model cannot override validation results.
2. **Explicit over Implicit:** All engineering states are modeled as a canonical, structured Design Intermediate Representation (IR). 
3. **No Silent Inventions:** Unsupported components or states must be flagged rather than hallucinated.

## High-Level Data Flow
1. **Student Natural Language Input:** The student provides a prompt (e.g., "Make a smart parking system...").
2. **AI Orchestrator:** The model clarifies ambiguities and coordinates retrieval.
3. **Curriculum/Registry Retrieval:** The system retrieves learning relationships, component specs, and prerequisite rules.
4. **Canonical Structured Design IR:** The AI maps the request into a strictly defined Design IR.
5. **Deterministic Engineering Tools:** 
    - *Validation:* Checks if the Design IR is syntactically and physically valid.
    - *Calculations/Simulations:* Computes behaviors using tools like ngspice, Verilator, etc.
    - *Compilation:* Compiles necessary firmware or RTL.
    - *Rendering:* Prepares the 2D/3D visual output.
6. **Student-Facing Output & Repair Loop:** The validated visualization, simulation results, and any validation errors are returned to the user, allowing for a feedback/repair loop.

## Separation between Probabilistic AI and Deterministic Engineering Systems
The system strictly isolates the LLM (probabilistic) from the validation, compilation, and simulation layers (deterministic). 
- AI outputs are treated as *untrusted proposals*.
- Validation layers (Python schemas, circuit rules, physical constraints) provide the absolute source of truth.
- If the AI proposes an invalid connection, the deterministic system rejects it and feeds the error back to the AI for a repair attempt.

## Major Subsystems
- **Knowledge/Curriculum Layer:** Maps concepts, prerequisites, and competency metadata.
- **Component/Asset Registry:** Houses definitions of physical, digital, and visualization objects.
- **AI Agent / Provider Layer:** Interacts with LLMs, orchestrates workflows, agnostic to specific providers.
- **Canonical Design IR:** The central state object describing a specific user design.
- **Validation/Simulation Adapters:** Bridges to simulators (ngspice, Wokwi, Verilator, etc.).
- **Rendering Layer:** Prepares visualization states (e.g., for Three.js/React).

## Expected Future Browser Architecture
Eventually, the backend will expose APIs for a web-based frontend. 
- The frontend will utilize tools like Three.js / React Three Fiber for rendering GLB/glTF 3D objects.
- It may run certain simulations locally (e.g., via WebAssembly) or rely on the backend.
- The state transferred between frontend and backend will be the Canonical Design IR.

## CLI-First Development Philosophy
To ensure the backend is robust, modular, and decoupled from frontend UI complexities, Phase 1 relies on a CLI-first approach. All workflows (validation, simulation, generation) must be executable and testable from the command line without requiring the browser layer.
