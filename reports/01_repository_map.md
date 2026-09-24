# Repository Map: Illustration Engine

## Overview
The Illustration Engine repository is structured as a Python package with separate concerns for domain models, AI orchestration, validation, component registry, curriculum, CLI, and frontend visualization.

## Directory Structure

```
/illustration-engine/
├── adapters/                     # Future adapters for simulation/rendering
│   ├── ai/                       # AI adapter implementations
│   ├── rendering/                # Rendering adapters
│   └── simulation/               # Simulation adapters
├── data/                         # Static data files
│   ├── assets/                   # Asset registry (placeholder)
│   ├── components/               # Component registry YAML files
│   │   ├── phase1-inventory.yaml # Legacy component inventory
│   │   └── registry.yaml         # Current component registry
│   ├── curriculum/               # Curriculum concept definitions
│   │   └── concepts.yaml         # Curriculum concepts
│   ├── fixtures/                 # Test fixtures (golden designs)
│   │   └── golden/               # Valid/invalid design test cases
│   └── relationships/            # Relationship mappings (placeholder)
├── docs/                         # Documentation
│   ├── architecture/             # Architectural decision records
│   ├── decisions/                # ADRs (Architecture Decision Records)
│   ├── research/                 # Open research questions
│   └── specs/                    # Detailed specifications
├── frontend/                     # Frontend visualization (React-based)
│   ├── dist/                     # Built distribution
│   ├── node_modules/             # npm dependencies
│   ├── public/                   # Static assets
│   └── src/                      # Source code
├── src/                          # Main source code
│   ├── adapters/                 # Adapter interfaces
│   ├── ai/                       # AI provider abstraction and implementations
│   │   ├── __init__.py
│   │   ├── models.py             # AI-specific data models
│   │   ├── orchestrator.py       # Main AI orchestration loop
│   │   ├── provider.py           # ModelProvider ABC interface
│   │   ├── provider_gemini.py    # Gemini API implementation
│   │   ├── provider_openai.py    # OpenAI API implementation
│   │   └── tools.py              # Tool definitions for AI orchestration
│   ├── cli/                      # Command-line interface
│   │   ├── __init__.py
│   │   └── main.py               # Typer-based CLI application
│   ├── components/               # Component registry and loading
│   │   ├── __init__.py
│   │   └── registry.py           # ComponentType registry from YAML
│   ├── core/                     # Domain models and enums
│   │   ├── __init__.py
│   │   ├── enums.py              # Standardized enumerations
│   │   └── models.py             # Pydantic models (DesignProject, etc.)
│   ├── curriculum/               # Curriculum knowledge store
│   │   ├── __init__.py
│   │   └── store.py              # Curriculum concept loading/search
│   ├── design/                   # Legacy/Provisional schema (Phase 1)
│   │   ├── __init__.py
│   │   └── schema.py             # Early Design IR experiments
│   └── validation/               # Deterministic validation engine
│       ├── __init__.py
│       ├── calculations.py       # LED resistor calculations (E24)
│   │   └── engine.py             # DesignValidator with all rules
├── tests/                        # Test suite
│   ├── integration/              # Integration tests
│   │   └── test_provider_real.py # Real provider tests
│   ├── unit/                     # Unit tests
│   │   ├── __init__.py
│   │   ├── test_agent_tools.py   # AI tool functionality
│   │   ├── test_calculations.py  # LED resistor calculations
│   │   ├── test_cli.py           # CLI command tests
│   │   ├── test_core_models.py   # Core Pydantic models
│   │   ├── test_curriculum.py    # Curriculum store
│   │   ├── test_orchestrator.py  # Orchestration loop
│   │   ├── test_provider.py      # Provider abstractions
│   │   ├── test_provider_gemini_schema.py # Gemini schema handling
│   │   ├── test_provider_gemini_serialization.py # Gemini serialization
│   │   ├── test_registry.py      # Component registry
│   │   ├── test_schema_serialization.py # Schema serialization
│   │   └── test_validation.py    # Validation engine
├── runs/                         # Orchestration traces and runs
├── scratch/                      # Temporary workspace
├── temp_render.py                # Legacy rendering script
└── pyproject.toml                # Project configuration and dependencies
```

## Key Files and Responsibilities

### Core Domain Models
- `src/core/models.py`: Pydantic models defining the Design Project IR
  - `DesignProject`: Top-level container for designs
  - `ComponentInstance`, `ComponentType`: Component definitions and usage
  - `PinDefinition`, `PinRef`, `Net`: Electrical connection modeling
  - `LogicRule`: Declarative functional logic
  - `ValidationResult`: Deterministic validation outcomes
  - `CurriculumContext`: Educational context tracking

- `src/core/enums.py`: Standardized enumerations
  - `ComponentCategory`: MICROCONTROLLER, SENSOR, etc.
  - `PinDirection`: INPUT, OUTPUT, POWER, GROUND, etc.
  - `ValidationStatus`: PASS, FAIL, UNVALIDATED
  - `ObjectType`: PHYSICAL, CIRCUIT_PRIMITIVE, etc.

### AI Orchestration
- `src/ai/provider.py`: Abstract `ModelProvider` base class
  - Defines interface: `generate()`, `structured_generate()`, `tool_call()`

- `src/ai/provider_gemini.py`: Gemini API implementation via REST
  - Handles message format conversion, schema sanitization
  - Implements tool calling and structured output

- `src/ai/provider_openai.py`: OpenAI API implementation
  - Similar structure to Gemini provider

- `src/ai/orchestrator.py`: Main AI engineering loop
  - Requirements extraction, tool usage, validation, repair logic
  - Manages conversation history, caching, metrics, tracing

- `src/ai/tools.py`: Tool definitions for AI orchestration
  - Component search, curriculum search, LED calculation, validation

### Component System
- `src/components/registry.py`: YAML-driven component registry
  - Loads components from `data/components/registry.yaml`
  - Provides search, lookup, and listing capabilities

- `data/components/registry.yaml`: 36 component definitions
  - Each with pin definitions, electrical properties, curriculum mapping

### Curriculum System
- `src/curriculum/store.py`: Curriculum concept store
  - Loads from `data/curriculum/concepts.yaml`
  - Provides search and lookup capabilities

- `data/curriculum/concepts.yaml`: 8 curriculum concepts
  - CMOS inverter, digital logic, FSM, RTL design, verification, etc.

### Validation Engine
- `src/validation/engine.py`: Deterministic DesignValidator
  - Implements 16 error codes (E001-E016) and 2 warnings (W001-W002)
  - Checks connectivity, voltage compatibility, LED requirements, etc.

- `src/validation/calculations.py`: Deterministic calculations
  - LED resistor calculation using E24 standard values

### CLI Interface
- `src/cli/main.py`: Typer-based command-line interface
  - Commands: component, curriculum, design, calc, agent, render
  - Exposes all functionality via terminal commands

### Testing
- `tests/unit/`: Comprehensive unit test suite (~2113 lines)
  - Tests for all subsystems: validation, calculations, models, etc.
- `tests/fixtures/golden/`: 9 JSON test fixtures
  - 1 valid smart parking design + 8 invalid variants for each error code

### Frontend (Parked)
- `frontend/`: React-based visualization (not actively maintained)
  - Consumes DesignProject JSON for 2D rendering
  - Entry points: `render web` and `render export` CLI commands

## Dependencies
See `pyproject.toml` for full dependency list:
- Core: pydantic, typer, PyYAML
- AI: Custom provider implementations (no direct SDK dependencies per ADR-002)
- Testing: pytest
- Frontend: React dependencies (in frontend/package.json)

## Conclusion
The repository follows a clean, modular architecture with well-separated concerns. The AI provider abstraction enables pluggable backends, the deterministic validation ensures correctness, and the YAML-driven registries allow extensibility. The system is designed to be CLI-first with no API key requirements for basic operation.