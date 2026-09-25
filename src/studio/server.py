"""Minimal JSON HTTP API for the studio (Python standard library only).

The server is stateless with respect to designs: the browser sends its StudioDocument with
every edit and receives the re-derived state. Only AI generation jobs are held in memory.
Bound to 127.0.0.1 by default; API keys never leave the server process.

Routes
  GET  /api/health                      GET  /api/providers
  GET  /api/library                     GET  /api/library/<component_type_id>
  GET  /api/patterns                    GET  /api/examples
  POST /api/examples/<id>               POST /api/open        {design}
  POST /api/state   {document}          POST /api/edit        {document, ops}
  POST /api/export/svg {document}       POST /api/generate    {prompt, provider?, model?}
  GET  /api/jobs/<job_id>
Anything else is served from frontend/dist (single-page-app fallback to index.html).
"""
from __future__ import annotations

import json
import mimetypes
import os
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlparse

from pydantic import TypeAdapter, ValidationError

from core.models import EngineeringDesignProject

from .document import StudioDocument
from .edits import EditError, EditOp
from .service import StudioService

DIST_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
_OPS = TypeAdapter(list[EditOp])
MAX_BODY = 5 * 1024 * 1024


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def make_handler(service: StudioService, static_dir: Optional[Path] = DIST_DIR):
    class Handler(BaseHTTPRequestHandler):
        server_version = "IllustrationEngineStudio/1.0"

        def log_message(self, fmt, *args):  # quiet default logging; errors are returned as JSON
            pass

        # ── helpers ──
        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, payload) -> None:
            self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                raise ApiError(413, "PAYLOAD_TOO_LARGE", "Request body too large")
            raw = self.rfile.read(length) if length else b"{}"
            try:
                data = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError as e:
                raise ApiError(400, "BAD_JSON", f"Invalid JSON: {e}")
            if not isinstance(data, dict):
                raise ApiError(400, "BAD_JSON", "Expected a JSON object")
            return data

        def _document(self, data: dict) -> StudioDocument:
            if "document" not in data:
                raise ApiError(400, "MISSING_DOCUMENT", "Request needs a 'document'")
            try:
                return StudioDocument.model_validate(data["document"])
            except ValidationError as e:
                raise ApiError(400, "BAD_DOCUMENT", str(e))

        def _dispatch(self, method: str) -> None:
            path = unquote(urlparse(self.path).path)
            try:
                if not path.startswith("/api/"):
                    if method != "GET":
                        raise ApiError(405, "METHOD_NOT_ALLOWED", "Only GET is supported here")
                    return self._static(path)
                self._api(method, path)
            except ApiError as e:
                self._json(e.status, {"error": {"code": e.code, "message": e.message}})
            except EditError as e:
                self._json(422, {"error": {"code": e.code, "message": e.message}})
            except Exception as e:  # pragma: no cover - defensive
                traceback.print_exc()
                self._json(500, {"error": {"code": "INTERNAL", "message": f"{type(e).__name__}: {e}"}})

        def _api(self, method: str, path: str) -> None:
            parts = [p for p in path.split("/")[2:] if p]
            if method == "GET" and parts == ["health"]:
                return self._json(200, {"ok": True})
            if method == "GET" and parts == ["providers"]:
                from ai.factory import available_providers
                return self._json(200, {"providers": available_providers()})
            if method == "GET" and parts == ["library"]:
                return self._json(200, {"components": service.library()})
            if method == "GET" and len(parts) == 2 and parts[0] == "library":
                comp = service.component(parts[1])
                if comp is None:
                    raise ApiError(404, "UNKNOWN_COMPONENT", f"No component '{parts[1]}'")
                return self._json(200, comp)
            if method == "GET" and parts == ["patterns"]:
                return self._json(200, {"patterns": service.patterns_list()})
            if method == "GET" and parts == ["examples"]:
                return self._json(200, {"examples": service.examples()})
            if method == "POST" and len(parts) == 2 and parts[0] == "examples":
                try:
                    return self._json(200, service.open_example(parts[1], bool(self._body().get("physical"))).model_dump(mode="json"))
                except KeyError:
                    raise ApiError(404, "UNKNOWN_EXAMPLE", f"No example '{parts[1]}'")
            if method == "POST" and parts == ["open"]:
                data = self._body()
                try:
                    design = EngineeringDesignProject.model_validate(data.get("design"))
                except ValidationError as e:
                    raise ApiError(400, "BAD_DESIGN", str(e))
                intent = None
                if data.get("intent") is not None:
                    from functional.intent import FunctionalIntent
                    try:
                        intent = FunctionalIntent.model_validate(data["intent"])
                    except ValidationError as e:
                        raise ApiError(400, "BAD_INTENT", str(e))
                return self._json(200, service.open_design(design, intent=intent, physical=bool(data.get("physical")))
                                  .model_dump(mode="json"))
            if method == "POST" and parts == ["state"]:
                data = self._body()
                return self._json(200, service.state(self._document(data), physical=bool(data.get("physical")))
                                  .model_dump(mode="json"))
            if method == "POST" and parts == ["edit"]:
                data = self._body()
                doc = self._document(data)
                try:
                    ops = _OPS.validate_python(data.get("ops", []))
                except ValidationError as e:
                    raise ApiError(400, "BAD_OPS", str(e))
                return self._json(200, service.apply(doc, ops, physical=bool(data.get("physical"))).model_dump(mode="json"))
            if method == "POST" and parts == ["export", "svg"]:
                from schematic.svg import render_svg
                state = service.state(self._document(self._body()))
                return self._send(200, render_svg(state.schematic).encode("utf-8"), "image/svg+xml")
            if method == "POST" and parts == ["generate"]:
                data = self._body()
                prompt = str(data.get("prompt", "")).strip()
                if not prompt:
                    raise ApiError(400, "EMPTY_PROMPT", "Describe the circuit you want")
                job = service.start_generation(prompt, data.get("provider"), data.get("model"))
                return self._json(202, {"job_id": job.job_id})
            if method == "GET" and len(parts) == 2 and parts[0] == "jobs":
                job = service.job(parts[1])
                if job is None:
                    raise ApiError(404, "UNKNOWN_JOB", "No such job")
                return self._json(200, job.as_dict())
            raise ApiError(404, "NOT_FOUND", f"No route {method} {path}")

        def _static(self, path: str) -> None:
            if static_dir is None or not static_dir.is_dir():
                raise ApiError(404, "NO_FRONTEND", "Frontend not built (run npm run build in frontend/)")
            target = (static_dir / path.lstrip("/")).resolve()
            if not target.is_relative_to(static_dir.resolve()) or not target.is_file():
                target = static_dir / "index.html"
            ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            self._send(200, target.read_bytes(), ctype)

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

    return Handler


def create_server(host: str = "127.0.0.1", port: int = 8765, service: Optional[StudioService] = None,
                  static_dir: Optional[Path] = DIST_DIR) -> ThreadingHTTPServer:
    service = service or StudioService()

    class _Server(ThreadingHTTPServer):
        # On Windows SO_REUSEADDR lets a second server bind the same port silently and requests
        # are then split between old and new processes. Refuse instead of sharing the port.
        allow_reuse_address = os.name != "nt"

    server = _Server((host, port), make_handler(service, static_dir))
    server.daemon_threads = True
    return server
