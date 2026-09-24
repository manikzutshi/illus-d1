"""Studio service layer - transport-independent (used by the HTTP server, CLI and tests)."""
from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Callable, Dict, List, Optional

from components.registry import ComponentRegistry, get_shared_registry
from core.models import EngineeringDesignProject
from curriculum.store import get_default_curriculum
from knowledge import get_default_patterns
from schematic import generate_schematic, placements_from_schematic, verify_schematic
from schematic.symbols import build_box_symbol, default_box_side, get_fixed_symbol, pin_mapping, symbol_name_for
from validation.engine import DesignValidator
from functional import FunctionalIntent, validate_function

from .document import OpResult, Provenance, StudioDocument, StudioState
from .edits import EditOp, apply_ops
from .explain import explain_design

EXAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "examples"


class StudioService:
    def __init__(self, registry: Optional[ComponentRegistry] = None,
                 provider_factory: Optional[Callable[[Optional[str], Optional[str]], object]] = None):
        self.registry = registry or get_shared_registry()
        self.curriculum = get_default_curriculum()
        self.patterns = get_default_patterns()
        self._provider_factory = provider_factory
        self.jobs: Dict[str, "GenerationJob"] = {}
        self._lock = threading.Lock()

    # ── derived state ─────────────────────────────────────────────────────
    def state(self, doc: StudioDocument, op_results: Optional[List[OpResult]] = None) -> StudioState:
        validation = DesignValidator(self.registry).validate(doc.design)
        functional = validate_function(doc.design, doc.intent, self.registry)
        schematic = generate_schematic(doc.design, self.registry, doc.layout)
        # Persist resolved placements so the next edit keeps the drawing stable.
        doc = doc.model_copy(deep=True)
        doc.layout.placements = placements_from_schematic(schematic, doc.layout)
        verification = verify_schematic(schematic, doc.design).as_dict()
        explanation = explain_design(doc.design, self.registry, validation, schematic, self.curriculum)
        explanation["function"] = functional.explanation or [i.statement for i in functional.inferred]
        return StudioState(document=doc, validation=validation, functional=functional, schematic=schematic,
                           verification=verification,
                           explanation=explanation, op_results=op_results or [])

    def open_design(self, design: EngineeringDesignProject, provenance: Optional[Provenance] = None,
                    intent: Optional[FunctionalIntent] = None) -> StudioState:
        return self.state(StudioDocument(design=design, intent=intent, provenance=provenance or Provenance(source="import")))

    def apply(self, doc: StudioDocument, ops: List[EditOp]) -> StudioState:
        new_doc, results = apply_ops(doc, ops, self.registry)
        return self.state(new_doc, results)

    # ── library / knowledge ───────────────────────────────────────────────
    def symbol_preview(self, ctype) -> dict:
        name = symbol_name_for(ctype)
        if name != "ic_box":
            sym = get_fixed_symbol(name)
            mapped = set(pin_mapping(ctype, sym).values())
            for p in sym.pins:
                p.hidden = p.name not in mapped
            return sym.model_dump()
        sides: Dict[str, list] = {"left": [], "right": [], "top": [], "bottom": []}
        fixed = ctype.symbol.box_sides if ctype.symbol else {}
        for p in ctype.pins:
            sides[fixed.get(p.pin_id, default_box_side(p.direction))].append((p.pin_id, p.pin_id, p.number))
        return build_box_symbol(f"preview:{ctype.component_type_id}", sides, title=ctype.short_name or ctype.name).model_dump()

    def library(self) -> List[dict]:
        out = []
        for ct in sorted(self.registry.list_all(), key=lambda c: (c.category.value, c.component_type_id)):
            out.append({
                "id": ct.component_type_id, "name": ct.name, "short_name": ct.short_name, "category": ct.category.value,
                "object_type": ct.object_type.value, "family": ct.family, "tags": ct.tags, "aliases": ct.aliases,
                "description": ct.description, "pin_count": len(ct.pins), "symbol": self.symbol_preview(ct),
            })
        return out

    def component(self, component_type_id: str) -> Optional[dict]:
        ct = self.registry.get(component_type_id)
        if ct is None:
            return None
        data = ct.model_dump()
        data["concepts"] = [{"concept_id": c.concept_id, "name": c.name, "kind": c.kind}
                            for c in self.curriculum.concepts_for_component(component_type_id)]
        return data

    def patterns_list(self) -> List[dict]:
        return [p.model_dump() for p in self.patterns.list_all()]

    def examples(self) -> List[dict]:
        out = []
        for path in sorted(EXAMPLES_DIR.glob("*.json")):
            d = json.loads(path.read_text(encoding="utf-8"))
            out.append({"id": path.stem, "name": d.get("name", path.stem), "description": d.get("description", ""),
                        "components": len(d.get("components", [])),
                        "concept": (d.get("curriculum_context") or {}).get("concept")})
        return out

    def open_example(self, example_id: str) -> StudioState:
        path = EXAMPLES_DIR / f"{example_id}.json"
        if not path.is_file() or path.parent != EXAMPLES_DIR:
            raise KeyError(example_id)
        design = EngineeringDesignProject.model_validate(json.loads(path.read_text(encoding="utf-8")))
        ipath = EXAMPLES_DIR / "intents" / f"{example_id}.json"
        intent = FunctionalIntent.model_validate(json.loads(ipath.read_text(encoding="utf-8"))) if ipath.is_file() else None
        return self.state(StudioDocument(design=design, intent=intent,
                                         provenance=Provenance(source="example", example=example_id)))

    # ── AI generation (background jobs) ───────────────────────────────────
    def start_generation(self, prompt: str, provider: Optional[str] = None, model: Optional[str] = None) -> "GenerationJob":
        job = GenerationJob(prompt=prompt, provider=provider, model=model)
        with self._lock:
            self.jobs[job.job_id] = job
        threading.Thread(target=self._run_generation, args=(job,), daemon=True).start()
        return job

    def _make_provider(self, provider: Optional[str], model: Optional[str]):
        if self._provider_factory is not None:
            return self._provider_factory(provider, model)
        from ai.factory import create_provider
        return create_provider(provider, model)

    def _run_generation(self, job: "GenerationJob") -> None:
        from ai.orchestrator import AgentState, Orchestrator
        provider_ref: list = []
        try:
            provider = self._make_provider(job.provider, job.model)
            provider_ref.append(provider)
            job.provider = job.provider or type(provider).__name__
            job.model = job.model or getattr(provider, "model_name", None)
            orch = Orchestrator(provider)
            provider_ref.append(orch)
            orch.verbose_callback = job.on_event
            design = orch.run(job.prompt)
            job.model = getattr(provider, "model_name", job.model)   # the model that actually answered
            job.trace_summary = {k: v for k, v in orch.metrics.items() if k != "start_time"}
            if design is not None:
                job.result = self.state(StudioDocument(design=design, intent=orch.functional_intent, provenance=Provenance(
                    source="ai", prompt=job.prompt, provider=job.provider, model=job.model)))
                job.status = "done"
            elif orch.state == AgentState.CLARIFICATION_REQUIRED:
                clar = next((t["data"] for t in reversed(orch.traces) if t["event"] == "CLARIFICATION_REQUIRED"), {})
                job.clarification = clar if isinstance(clar, dict) else {"reason": str(clar)}
                job.status = "clarification"
            else:
                last = next((t["data"] for t in reversed(orch.traces) if t["event"] == "VALIDATION_RESULT"), None)
                job.last_attempt = _last_draft(orch.traces)
                job.error = "The AI could not produce a design that passes deterministic validation."
                msgs = [e.get("message", "") for e in last.get("errors", [])[:5]] if isinstance(last, dict) else []
                func = getattr(orch, "last_functional_report", None)
                if func is not None:
                    msgs += [f"{f.code} {f.message}" for f in func.blocking()[:5]]
                if msgs:
                    job.error += " Last errors: " + "; ".join(msgs)
                job.status = "failed"
        except Exception as e:  # provider/network errors surface to the user, never crash the server
            job.error = f"{type(e).__name__}: {e}"
            job.status = "failed"
        finally:
            if provider_ref:
                job.model = getattr(provider_ref[0], "model_name", job.model)
            if len(provider_ref) > 1 and not job.trace_summary:
                job.trace_summary = {k: v for k, v in provider_ref[1].metrics.items() if k != "start_time"}
            job.finished_at = time.time()

    def job(self, job_id: str) -> Optional["GenerationJob"]:
        return self.jobs.get(job_id)


class GenerationJob:
    def __init__(self, prompt: str, provider: Optional[str], model: Optional[str]):
        self.job_id = uuid.uuid4().hex[:12]
        self.prompt = prompt
        self.provider = provider
        self.model = model
        self.status = "running"
        self.events: List[dict] = []
        self.result: Optional[StudioState] = None
        self.error: Optional[str] = None
        self.clarification: Optional[dict] = None
        self.last_attempt: Optional[dict] = None     # last rejected draft of a failed job, for diagnosis
        self.intent_snapshot: Optional[dict] = None  # the functional intent the drafts were graded against
        self.trace_summary: dict = {}
        self.started_at = time.time()
        self.finished_at: Optional[float] = None

    def on_event(self, event: str, data) -> None:
        if event == "FUNCTIONAL_INTENT" and isinstance(data, dict):
            self.intent_snapshot = data.get("intent")
        self.events.append({"t": round(time.time() - self.started_at, 2), "event": event, "message": summarize_event(event, data)})

    def as_dict(self, include_result: bool = True) -> dict:
        out = {"job_id": self.job_id, "status": self.status, "prompt": self.prompt, "provider": self.provider,
               "model": self.model, "events": self.events, "error": self.error, "clarification": self.clarification, "last_attempt": self.last_attempt,
               "trace_summary": self.trace_summary,
               "elapsed_s": round((self.finished_at or time.time()) - self.started_at, 1)}
        if include_result and self.result is not None:
            out["result"] = self.result.model_dump(mode="json")
        return out


def _last_draft(traces) -> Optional[dict]:
    """The most recent design the AI proposed or asked to validate, with the intent it was graded against."""
    for t in reversed(traces):
        if t["event"] == "PROPOSED_DESIGN" and isinstance(t["data"], dict):
            return t["data"]
        if t["event"] == "TOOL_CALL" and isinstance(t["data"], dict) and t["data"].get("tool") == "validate_design":
            d = t["data"].get("args", {}).get("design")
            if isinstance(d, dict):
                return d
    return None


def summarize_event(event: str, data) -> str:
    if event == "USER_PROMPT":
        return "Reading the request"
    if event == "REQUIREMENTS_EXTRACTED" and isinstance(data, dict):
        return f"Understood intent: {data.get('intent', '')}"
    if event == "FUNCTIONAL_INTENT" and isinstance(data, dict):
        beh = (data.get("intent") or {}).get("behaviors", [])
        parts = []
        for b in beh[:3]:
            w, t = b.get("when", {}), b.get("then", {})
            parts.append(f"{t.get('output')} {t.get('effect')} when {w.get('input') or ''} {w.get('relation')}".replace("  ", " "))
        return "Required behaviour: " + ("; ".join(parts) if parts else "(none extracted)")
    if event == "FUNCTIONAL_RESULT" and isinstance(data, dict):
        fails = [f for f in data.get("findings", []) if f.get("status") == "FAIL"]
        if fails:
            return f"Functional check → FAIL: " + "; ".join(f"{f.get('code')} {f.get('message', '')[:140]}" for f in fails[:3])
        return f"Functional check → {data.get('status')}"
    if event == "REQUIREMENTS_EXTRACTION_FAILED":
        return "Requirement extraction failed; continuing with the raw request"
    if event == "TOOL_CALL" and isinstance(data, dict):
        tool, args = data.get("tool"), data.get("args", {})
        if tool == "search_components":
            return f"Searching the component library for “{args.get('query', '')}”"
        if tool == "get_component":
            return f"Reading datasheet facts for {args.get('component_id', '')}"
        if tool == "validate_design":
            try:
                res = json.loads(data.get("result", "{}"))
            except Exception:
                res = {}
            status = res.get("status") if isinstance(res, dict) else None
            if status is None:
                return "Checking a draft design with the deterministic validator → not a readable design (rejected)"
            if str(res.get("overall", "")).startswith("REJECTED"):
                return f"Checking a draft design with the deterministic validator → {status} electrically, functional FAIL"
            return f"Checking a draft design with the deterministic validator → {status}"
        if tool in ("search_patterns", "get_pattern"):
            return f"Looking up design pattern “{args.get('query') or args.get('pattern_id', '')}”"
        if tool == "calculate":
            return f"Calculating {args.get('calculation', '')}"
        return f"Using tool {tool}"
    if event == "PROPOSAL_REQUESTED" and isinstance(data, dict):
        n = data.get("attempt", 0)
        return "Drafting the engineering design" if n == 0 else f"Repairing the design (attempt {n})"
    if event == "VALIDATION_RESULT" and isinstance(data, dict):
        codes = [e.get("code") for e in data.get("errors", [])]
        status = getattr(data.get("status"), "value", data.get("status"))
        return f"Validation {status}" + (f": {', '.join(codes)}" if codes else "")
    if event == "PROPOSED_DESIGN" and isinstance(data, dict):
        return f"Draft design proposed: {len(data.get('components', []))} parts, {len(data.get('nets', []))} nets"
    if event == "CLARIFICATION_REQUIRED":
        return "The AI needs clarification"
    if event == "COMPLETED":
        return "Design validated"
    if event == "FAILED":
        return "Could not reach a valid design"
    return event
