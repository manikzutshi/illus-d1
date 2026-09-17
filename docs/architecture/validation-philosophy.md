# Validation Philosophy

The core constraint of the Engineering Visualization Engine is that **the LLM is not the source of engineering truth.** 

## Principles of Validation

1. **AI Proposes:** The AI acts as an intelligent router and synthesizer. It interprets user intent and proposes a Design IR (Intermediate Representation) based on the Component Registry and Learning Graph.
2. **Deterministic Validators Decide Validity:** Python schemas (e.g., Pydantic), Electrical Rule Checks (ERC), and Design Rule Checks (DRC) verify if the proposed Design IR is semantically and physically valid.
3. **Simulation Decides Executable Behavior:** The AI does not predict waveform outputs. A deterministic simulator (e.g., ngspice, Wokwi, Verilator) evaluates the Design IR and generates the behavioral data.
4. **Compiler Decides Code Compilability:** If firmware or RTL is generated, standard toolchains (GCC, Yosys) determine if the code is valid.
5. **Renderer Decides Visual Output:** The 3D/2D visual state is deterministically constructed from the Design IR and Asset Registry. The AI does not generate the pixel data.
6. **The Model Cannot Override Validation Results:** If a validator flags an error (e.g., "Short circuit detected between VCC and GND"), the AI cannot force the system to accept it. The AI must be fed the error and attempt to propose a repaired Design IR.
