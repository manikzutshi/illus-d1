# ADR 002: Provider-Agnostic AI Architecture

## Context
The system relies heavily on LLMs to parse natural language, orchestrate retrieval, and propose the Design IR. The landscape of AI models is highly volatile, with frequent releases of new frontier models, cost reductions, and improvements in open-weight models.

## Decision
The core engine must be designed to be completely **Provider-Agnostic**. The architecture must support:
- **Frontier Hosted APIs:** (e.g., GPT-4o, Claude 3.5 Sonnet, Gemini 1.5 Pro) for complex reasoning and planning.
- **Cheaper Hosted Models:** (e.g., GPT-4o-mini, Claude 3 Haiku, Gemini 1.5 Flash) for simple schema mapping, parsing, or specific sub-agent tasks.
- **Local / Open Models:** (e.g., Llama 3, Mistral) for offline capabilities, data privacy, and zero-inference-cost deployments.

No single final model is selected at this stage. 

## Consequences
- The application will utilize an abstraction layer (e.g., LiteLLM or a custom ModelProvider interface) instead of depending directly on `openai` or `anthropic` Python packages.
- Prompts and system instructions must be written generally enough to work across different model families, or prompt templates must be conditionally resolved based on the active provider.
- We must maintain the ability to test the system with mock providers without requiring API keys.
