# Open Architectural Questions

The following decisions remain unresolved and require further research during the next phases of implementation:

## Engineering & Simulation
- **Exact Simulation Backend:** Which engine to use for embedded simulation (e.g., Wokwi CLI vs Wokwi Web vs QEMU).
- **Verilator Execution Model:** How to securely compile and run Verilog tests.
- **SPICE Execution Model:** `ngspice` vs `xyce`, and how to interface it with the Design IR.
- **Wokwi Integration Method:** Should we run simulations entirely in the browser using WebAssembly or remotely on the backend?

## Rendering
- **Exact Rendering Stack:** Three.js vs React Three Fiber vs Babylon.js.
- **Component Asset Sources:** Where to source high-quality, educationally accurate 3D GLB models and 2D SVGs.
- **Educational Asset Licensing:** Ensuring all visual assets comply with open-source/CC licensing constraints.

## AI & Orchestration
- **Canonical IR Design:** Finalizing the schema for the Design IR (e.g., JSON Schema vs Pydantic specifics).
- **Hosted vs Local Model Mix:** Finding the exact balance between inference cost and capability.
- **Model Routing:** How to dynamically route tasks (e.g., semantic search vs code generation) to the optimal model.

## Infrastructure & Security
- **Browser vs Backend Simulation:** The trade-offs of heavy client-side WASM vs backend server costs.
- **Security Sandbox:** How to safely compile and execute AI-generated firmware (e.g., C++ for ESP32) or RTL (Verilog) without exposing the host to malicious code (e.g., gVisor, Firecracker microVMs, or strict Docker containers).
- **Deployment Architecture:** Serverless vs persistent stateful containers for managing long-running interactive sessions.
