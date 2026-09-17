# Learning Relationship Graph

This document describes the minimal knowledge graph connecting educational concepts to engineering artifacts. We are avoiding heavy semantic web standards (OWL/RDF) in Phase 1 in favor of simple, traversable JSON/YAML structures.

## Core Nodes

- **Concepts:** The fundamental ideas being taught (e.g., "Ohm's Law", "Pull-up Resistors", "I2C Protocol").
- **Components:** Physical or logical parts (e.g., `resistor`, `esp32`).
- **Projects:** Capstone or mini-projects combining multiple concepts (e.g., "Smart Parking System").
- **Tools:** Engineering tools used in the curriculum (e.g., "Oscilloscope", "Wokwi", "Verilator").
- **Standards:** Industry standards (e.g., "IEEE 802.11", "JEDEC").

## Node Properties and Relationships

Each Concept node in the graph will typically contain:

- **ID:** Unique identifier (e.g., `concept_pull_up_resistor`).
- **Name:** Human-readable name.
- **Prerequisites:** List of Concept IDs required before this one (e.g., `concept_ohms_law`, `concept_digital_logic`).
- **Related Concepts:** Sibling or adjacent concepts.
- **Components Introduced:** List of component canonical IDs (e.g., `resistor_10k`).
- **Visualization Tasks:** Specific rendering views associated with learning this concept (e.g., showing current flow in a 3D view).
- **Simulation Tasks:** Specific simulation configurations needed to prove the concept.
- **Debug Tasks:** Pre-configured broken states of the Design IR that the student must fix.
- **Optimization Tasks:** Exercises where a working design must be improved (e.g., lower power consumption).
- **Competency Levels:** The expected depth of knowledge (Beginner vs. Advanced implementation).
- **Role Mappings:** How this concept maps to industry roles (e.g., "Embedded Software Engineer", "Verification Engineer").

## Usage
The AI Orchestrator uses this graph to:
1. Ensure the generated Design IR matches the student's current competency level.
2. Select appropriate debug scenarios.
3. Prevent hallucination by strictly drawing from valid related concepts and components.
