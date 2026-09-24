import json
import os
import urllib.request
import urllib.error
from typing import Type, Optional, Any
from pydantic import BaseModel

from .provider import ModelProvider

class RESTGeminiProvider(ModelProvider):
    """A generic REST provider that communicates with the official Gemini API."""
    
    DEFAULT_MODEL = "gemini-3.5-flash"
    TIMEOUT_S = 150
    RETRIES = 2
    MAX_RATE_LIMIT_WAITS = 6

    def __init__(self, model_name: Optional[str] = None, api_key: Optional[str] = None,
                 fallback_models: Optional[list] = None):
        self.model_name = model_name or self.DEFAULT_MODEL
        # Tried in order when the current model is overloaded (503) or unavailable (404).
        self.fallback_models = [m for m in (fallback_models or []) if m != self.model_name]
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable is not set")
            
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        
    def _convert_messages(self, messages: list[dict]) -> tuple[list[dict], Optional[dict]]:
        """Converts OpenAI-style messages to Gemini format."""
        contents = []
        system_instruction = None
        
        for msg in messages:
            role = msg["role"]
            if role == "system":
                system_instruction = {"parts": [{"text": msg["content"]}]}
            elif role == "user":
                if contents and contents[-1]["role"] == "user":
                    contents[-1]["parts"].append({"text": msg["content"]})
                else:
                    contents.append({"role": "user", "parts": [{"text": msg["content"]}]})
            elif role == "assistant":
                if "raw_parts" in msg:
                    parts = msg["raw_parts"]
                elif msg.get("tool_calls"):
                    parts = []
                    for tc in msg["tool_calls"]:
                        parts.append({
                            "functionCall": {
                                "name": tc["function"]["name"],
                                "args": json.loads(tc["function"]["arguments"])
                            }
                        })
                else:
                    parts = [{"text": msg.get("content", "")}]
                
                # Gemini forbids consecutive model turns, merge if needed
                if contents and contents[-1]["role"] == "model":
                    contents[-1]["parts"].extend(parts)
                else:
                    contents.append({"role": "model", "parts": parts})
                    
            elif role == "tool":
                parsed = None
                try:
                    parsed = json.loads(msg["content"])
                except Exception:
                    pass
                
                if isinstance(parsed, dict):
                    response_obj = parsed
                elif isinstance(parsed, list):
                    response_obj = {"result": parsed}
                else:
                    response_obj = {"result": msg["content"]}
                    
                func_resp = {
                    "name": msg["name"],
                    "response": response_obj
                }
                
                # Preserve ID if it exists and wasn't automatically fabricated by us
                if "tool_call_id" in msg and msg["tool_call_id"] != "call_" + msg["name"]:
                    func_resp["id"] = msg["tool_call_id"]
                    
                part = {"functionResponse": func_resp}
                if contents and contents[-1]["role"] == "user":
                    contents[-1]["parts"].append(part)
                else:
                    contents.append({"role": "user", "parts": [part]})
                
        return contents, system_instruction

    def _sanitize_schema(self, node: dict) -> dict:
        """Recursively strip unsupported JSON Schema keys for Gemini Function Declarations."""
        if not isinstance(node, dict):
            return node
            
        result = {}
        
        # Flatten anyOf/allOf
        if "anyOf" in node:
            for option in node["anyOf"]:
                if isinstance(option, dict) and option.get("type") != "null":
                    result.update(self._sanitize_schema(option))
                    break
        elif "allOf" in node and node["allOf"]:
            result.update(self._sanitize_schema(node["allOf"][0]))
            
        supported_keys = ["type", "description", "properties", "items", "required", "enum", "format"]
        
        for key in supported_keys:
            if key in node:
                if key == "properties":
                    result["properties"] = {k: self._sanitize_schema(v) for k, v in node["properties"].items()}
                elif key == "items":
                    result["items"] = self._sanitize_schema(node["items"])
                else:
                    result[key] = node[key]
                    
        # Infer types if missing but shape is obvious
        if "properties" in result and "type" not in result:
            result["type"] = "object"
        if "items" in result and "type" not in result:
            result["type"] = "array"
            
        return result

    def _convert_tools(self, tools: list[dict]) -> list[dict]:
        """Converts OpenAI-style tools to Gemini format."""
        if not tools:
            return []
        
        gemini_tools = []
        for tool in tools:
            fn = tool["function"]
            params = fn.get("parameters", {})
            if params:
                params = self._sanitize_schema(params)
                
            gemini_tools.append({
                "name": fn["name"],
                "description": fn.get("description", ""),
                "parameters": params
            })
            
        return [{"functionDeclarations": gemini_tools}]
        
    OVERLOAD_ROUNDS = 3
    OVERLOAD_PAUSE_S = 20

    def _post(self, payload: dict) -> dict:
        """POST with model fallback. 503 (overloaded / timed out) moves to the next candidate model;
        when every candidate is overloaded, pause and cycle again (overload spikes are short)."""
        import time
        candidates = [self.model_name] + list(self.fallback_models)
        rounds = 0
        while True:
            try:
                return self._post_once(payload)
            except RuntimeError as e:
                code = str(e)[17:20] if str(e).startswith("Gemini API Error") else ""
                daily = code == "429" and "daily quota" in str(e)
                if (code == "404" or daily) and self.model_name in candidates and len(candidates) > 1:
                    # retired model or its daily quota is gone: never retry it in this session
                    idx = candidates.index(self.model_name)
                    candidates.remove(self.model_name)
                    self.model_name = candidates[min(idx, len(candidates) - 1)]
                    continue
                if code in ("503", "404") and len(candidates) > 1:
                    idx = candidates.index(self.model_name) if self.model_name in candidates else -1
                    if idx + 1 < len(candidates):
                        self.model_name = candidates[idx + 1]
                        continue
                    if rounds < self.OVERLOAD_ROUNDS:
                        rounds += 1
                        time.sleep(self.OVERLOAD_PAUSE_S)
                        self.model_name = candidates[0]
                        continue
                raise

    def _post_once(self, payload: dict) -> dict:
        # The key travels in a header, never in the URL, so it cannot leak through logged URLs
        # or exception messages.
        url = f"{self.base_url}/models/{self.model_name}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
        }
        data = json.dumps(payload).encode("utf-8")
        import re
        import time
        rate_limit_waits = 0
        attempt = 0
        while True:
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=self.TIMEOUT_S) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                error_body = e.read().decode("utf-8", errors="replace")
                if e.code == 429 and rate_limit_waits < self.MAX_RATE_LIMIT_WAITS:
                    # Honour the server's RetryInfo (per-minute quotas reset quickly).
                    m = re.search(r'"retryDelay":\s*"(\d+(?:\.\d+)?)s"', error_body)
                    delay = min(float(m.group(1)) + 1.0, 70.0) if m else 20.0
                    if "PerDay" in error_body:
                        raise RuntimeError(f"Gemini API Error 429 (daily quota exhausted): {error_body[:600]}")
                    rate_limit_waits += 1
                    time.sleep(delay)
                    continue
                if e.code == 503 and self.fallback_models is not None and len(self.fallback_models) > 0:
                    raise RuntimeError(f"Gemini API Error {e.code}: {error_body[:600]}")  # switch model now
                if e.code in (500, 502, 503, 504) and attempt < self.RETRIES:
                    attempt += 1
                    time.sleep(2 * attempt)
                    continue
                raise RuntimeError(f"Gemini API Error {e.code}: {error_body[:2000]}")
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                if isinstance(e, TimeoutError) or "timed out" in str(getattr(e, "reason", e)):
                    if self.fallback_models:
                        raise RuntimeError("Gemini API Error 503: request timed out")  # try the next model
                if attempt < self.RETRIES:
                    attempt += 1
                    time.sleep(2 * attempt)
                    continue
                raise RuntimeError(f"Gemini API unreachable or timed out: {getattr(e, 'reason', e)}")

    def generate(self, messages: list[dict], context: Optional[dict] = None) -> str:
        contents, system_instruction = self._convert_messages(messages)
        payload = {
            "contents": contents,
            "generationConfig": {"temperature": 0.2}
        }
        if system_instruction:
            payload["systemInstruction"] = system_instruction
            
        result = self._post(payload)
        
        try:
            parts = result["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts if not p.get("thought"))
        except (KeyError, IndexError):
            return ""
        
    def structured_generate(self, messages: list[dict], schema: Type[BaseModel], context: Optional[dict] = None) -> BaseModel:
        contents, system_instruction = self._convert_messages(messages)
        if hasattr(schema, "resolved_schema"):
            schema_json = schema.resolved_schema()
        else:
            schema_json = schema.model_json_schema()
            
        schema_json = self._sanitize_schema(schema_json)
            
        gemini_tools = [{
            "functionDeclarations": [{
                "name": "submit_structured_output",
                "description": f"Submit the final structured {schema.__name__}",
                "parameters": schema_json
            }]
        }]
        
        payload = {
            "contents": contents,
            "tools": gemini_tools,
            "toolConfig": {
                "functionCallingConfig": {
                    "mode": "ANY",
                    "allowedFunctionNames": ["submit_structured_output"]
                }
            },
            "generationConfig": {"temperature": 0.2}
        }
        if system_instruction:
            payload["systemInstruction"] = system_instruction
            
        result = self._post(payload)
        
        try:
            parts = result["candidates"][0]["content"]["parts"]
            part = next((p for p in parts if "functionCall" in p), parts[0])
            if "functionCall" in part:
                args = part["functionCall"].get("args", {})
                # Gemini returns the object directly, we don't need to json.loads it
                return schema.model_validate(args)
            
            text = part.get("text", "")
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            data = json.loads(text)
            return schema.model_validate(data)
        except Exception as e:
            raise ValueError(f"Failed to generate structured output for {schema.__name__}. Error: {e}, Result: {result}")

    def tool_call(self, messages: list[dict], tools: list[dict], context: Optional[dict] = None) -> Any:
        contents, system_instruction = self._convert_messages(messages)
        gemini_tools = self._convert_tools(tools)
        
        payload = {
            "contents": contents,
            "tools": gemini_tools,
            "generationConfig": {"temperature": 0.2}
        }
        if system_instruction:
            payload["systemInstruction"] = system_instruction
            
        result = self._post(payload)
        
        try:
            part = result["candidates"][0]["content"]["parts"][0]
            all_parts = result["candidates"][0]["content"]["parts"]
            
            if "functionCall" in part or any("functionCall" in p for p in all_parts):
                # Convert back to OpenAI format so orchestrator doesn't need to change
                tool_calls = []
                for p in all_parts:
                    if "functionCall" in p:
                        fc = p["functionCall"]
                        tool_calls.append({
                            "id": fc.get("id", "call_" + fc["name"]),
                            "type": "function",
                            "function": {
                                "name": fc["name"],
                                "arguments": json.dumps(fc.get("args", {}))
                            }
                        })
                return {"role": "assistant", "content": None, "tool_calls": tool_calls, "raw_parts": all_parts}
            else:
                return {"role": "assistant", "content": part.get("text", ""), "raw_parts": all_parts}
        except (KeyError, IndexError):
            return {"role": "assistant", "content": ""}
