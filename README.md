# Illustration Engine

**Phase 2 — Educational Semiconductor Engineering Visualization Engine**

A curriculum-grounded, deterministic engineering foundation for interactive VLSI / electronics education. Students describe an engineering project in natural language; the system resolves components, validates the design, calculates circuit values, and prepares simulation — all backed by deterministic tools rather than LLM hallucination.

## Architectural Philosophy

- **AI Proposes, Determinism Disposes.** The AI generates a structured Design IR. Deterministic validators, calculators, and simulators decide if it's valid.
- **No Silent Inventions.** Unsupported components are rejected, not hallucinated.
- **Provider Agnostic.** No direct dependency on OpenAI/Anthropic/Gemini SDKs.
- **CLI-First.** Everything is testable from the command line with no frontend or API key.

## Quickstart

```bash
cd illustration-engine
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # Windows
pip install -e .

# Run tests (100 tests)
pytest

# Validate the golden smart-parking design
illustration-engine design validate tests/fixtures/golden/smart_parking_valid.json

# List all registered components
illustration-engine component list

# Show component details
illustration-engine component show board:esp32-devkit-v1

# Search components
illustration-engine component search led

# Calculate an LED series resistor
illustration-engine calc led-resistor --supply 3.3 --vf 2.0 --current 10

# Search curriculum concepts
illustration-engine curriculum search "CMOS inverter"
```

## Project Structure

```
illustration-engine/
├── src/
│   ├── core/           # Domain models (Pydantic) and enums
│   ├── components/     # Component registry loader
│   ├── curriculum/     # Curriculum concept store
│   ├── validation/     # Deterministic validator + calculation service
│   ├── ai/             # Provider abstraction + mock + agent tool boundary
│   ├── cli/            # Typer CLI (real commands)
│   └── design/         # Provisional schema (Phase 1 legacy)
├── data/
│   ├── components/     # Component registry YAML (8 types)
│   └── curriculum/     # Curriculum concepts YAML (8 concepts)
├── tests/
│   ├── unit/           # 100 tests covering all subsystems
│   └── fixtures/golden/# 6 golden Design IR fixtures
├── docs/
│   ├── architecture/   # System overview, validation philosophy, model provider
│   ├── decisions/      # ADR-001 through ADR-003
│   ├── specs/          # Design IR, component registry, asset registry, learning graph
│   └── research/       # Open architectural questions
├── adapters/           # Future simulation/rendering adapters
└── pyproject.toml
```

## Key Subsystems

| Subsystem | Status | Module |
|-----------|--------|--------|
| Domain Models (Pydantic v2) | ✅ Implemented | `src/core/` |
| Component Registry (YAML-driven) | ✅ Implemented | `src/components/` |
| Curriculum Store | ✅ Implemented | `src/curriculum/` |
| Deterministic Validator (E001-E009, W001) | ✅ Implemented | `src/validation/engine.py` |
| LED Resistor Calculator (E24) | ✅ Implemented | `src/validation/calculations.py` |
| CLI (component/design/calc/curriculum) | ✅ Implemented | `src/cli/main.py` |
| Provider Abstraction + Mock | ✅ Implemented | `src/ai/provider.py` |
| Agent Tool Boundary | ✅ Stubbed | `src/ai/tools.py` |
| Real LLM Provider | 🔲 Not yet | — |
| Wokwi/SPICE Simulation | 🔲 Not yet | — |
| 3D Rendering | 🔲 Not yet | — |
| Web Frontend | 🔲 Not yet | — |

## Validation Error Codes

| Code | Name | Severity |
|------|------|----------|
| E001 | UNKNOWN_COMPONENT_TYPE | ERROR |
| E002 | UNKNOWN_PIN | ERROR |
| E003 | DUPLICATE_INSTANCE_ID | ERROR |
| E004 | MISSING_POWER | ERROR |
| E005 | MISSING_GROUND | ERROR |
| E006 | INVALID_CONNECTION_ENDPOINT | ERROR |
| E007 | LED_REQUIRES_RESISTOR | ERROR |
| E008 | DUPLICATE_NET_ID | ERROR |
| E009 | DISCONNECTED_COMPONENT | ERROR |
| W001 | MISSING_RESISTOR_VALUE | WARNING |
