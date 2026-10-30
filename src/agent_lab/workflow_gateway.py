"""Loopback-only provider admission and allowlisted MCP tools for OpenCode.

The child has no upstream keys. Every generation (including helper generations)
passes this gate. Responses are buffered until complete usage is recorded, so
truncated/unaccounted output cannot execute tools. No upstream request is retried.
"""
from contextlib import contextmanager
from dataclasses import asdict
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import secrets
import threading
import time
import urllib.request
from .accounting import Ledger, StopRun
from .domain import save_json, ToolCall
from .providers import make_provider, NoRedirect, ProviderError
from .token_counting import TokenCountError
from .tools import TOOLS, execute

CLARIFY = {"name": "request_clarification", "description": "Pause the experiment if task information is genuinely missing. No answer is fabricated.",
           "parameters": {"type": "object", "properties": {"question": {"type": "string"}},
                          "required": ["question"], "additionalProperties": False}}


def role_tool_definitions(role):
    if role not in {"solo", "planner", "worker"}:
        raise ValueError("Unknown experiment role")
    return [tool for tool in [*TOOLS, CLARIFY]
            if tool["name"] != "submit" and (role != "planner" or tool["name"] != "write_file")]


def stream_result(provider, events):
    """Extract the complete native response's accounting without rewriting SSE."""
    if provider == "deepseek":
        usage = next((e["usage"] for e in reversed(events) if e.get("usage")), None)
        finish = [c.get("finish_reason") for e in events for c in e.get("choices", [])]
        calls = {c.get("id") for e in events for choice in e.get("choices", [])
                 for c in choice.get("delta", {}).get("tool_calls", []) if c.get("id")}
        if not any(finish):
            raise ValueError("Missing terminal chat completion")
        return {"id": events[0].get("id", ""), "model": events[0].get("model", ""),
                "usage": usage, "choices": [{"finish_reason": "length" if "length" in finish else "stop"}],
                "_lab_tool_calls": len(calls)}
    if provider == "openai":
        response = next((e["response"] for e in reversed(events)
                         if e.get("type") in {"response.completed", "response.incomplete", "response.failed"}), None)
        if response is None:
            raise ValueError("Missing terminal Responses event")
        return {**response, "_lab_tool_calls": sum(i.get("type") == "function_call" for i in response.get("output", []))}
    start = next((e["message"] for e in events if e.get("type") == "message_start"), None)
    if start is None or not any(e.get("type") == "message_stop" for e in events):
        raise ValueError("Missing terminal Messages event")
    raw = {**start, "usage": dict(start.get("usage", {}))}
    for event in events:
        if event.get("type") == "message_delta":
            raw["usage"].update(event.get("usage", {}))
            raw.update(event.get("delta", {}))
    raw["_lab_tool_calls"] = sum(e.get("type") == "content_block_start" and e.get("content_block", {}).get("type") == "tool_use" for e in events)
    return raw


def forward_stream(provider, payload, timeout):
    endpoints = {"deepseek": "https://api.deepseek.com/chat/completions",
                 "openai": "https://api.openai.com/v1/responses",
                 "anthropic": "https://api.anthropic.com/v1/messages"}
    key = provider._api_key
    headers = ({"x-api-key": key, "anthropic-version": "2023-06-01"}
               if provider.model.provider == "anthropic" else {"Authorization": "Bearer " + key})
    request = urllib.request.Request(endpoints[provider.model.provider],
        data=json.dumps(payload, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json", **headers}, method="POST")
    deadline = time.monotonic() + timeout
    chunks = []
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            while True:
                if time.monotonic() >= deadline:
                    raise TimeoutError
                chunk = response.read1(65536)
                if not chunk:
                    break
                chunks.append(chunk)
                if sum(map(len, chunks)) > 16 * 1024 * 1024:
                    raise ValueError("Response too large")
        body = b"".join(chunks)
        events = []
        for block in body.decode("utf-8").replace("\r\n", "\n").split("\n\n"):
            data = "\n".join(line[5:].strip() for line in block.splitlines() if line.startswith("data:"))
            if data and data != "[DONE]":
                events.append(json.loads(data))
        return body, stream_result(provider.model.provider, events)
    except Exception as exc:
        raise ProviderError(f"Upstream stream failed ({type(exc).__name__}); usage may be unknown") from None


class Gateway:
    def __init__(self, task, models, limits, directory, recorder, workspace, checks):
        self.models = models
        self.clients = {m.id: make_provider(m, "", "", [], task) for m in models}
        self.ledger = Ledger(limits)
        self.limits, self.directory, self.recorder = limits, directory, recorder
        self.workspace, self.checks = workspace, checks
        self.lock = threading.RLock()
        self.started = time.monotonic()
        self.halted = ""
        self.turn = None
        self.allow_write = False
        self.closed = True
        self.active_role = None
        self.active_model_id = None
        self.secret = secrets.token_urlsafe(24)

    def remaining(self):
        left = self.limits.max_seconds - (time.monotonic() - self.started)
        if left <= 0:
            raise StopRun("time_limit")
        return left

    def guard(self):
        if self.halted:
            raise StopRun(self.halted)
        if self.closed:
            raise StopRun("outside_user_turn")
        self.remaining()

    def generation(self, model_id, path, payload):
        with self.lock:
            self.guard()
            if self.active_model_id is not None and model_id != self.active_model_id:
                raise StopRun("unexpected_model")
            if model_id not in self.clients:
                raise StopRun("unexpected_model")
            provider = self.clients[model_id]
            model = provider.model
            expected = {"openai": "responses", "deepseek": "chat/completions", "anthropic": "messages"}[model.provider]
            if path != expected or payload.get("model") != model.model:
                raise StopRun("unexpected_provider_request")
            payload = dict(payload)
            # The catalog, not OpenCode defaults, owns generation parameters.
            payload["stream"] = True
            if model.provider == "openai":
                payload["max_output_tokens"] = model.max_output_tokens
                payload["reasoning"] = {"effort": model.reasoning_effort}
                payload["store"] = False
                payload["include"] = ["reasoning.encrypted_content"]
                payload.setdefault("instructions", "")
                payload.setdefault("tools", [])
            else:
                payload["max_tokens"] = model.max_output_tokens
                if model.provider == "deepseek":
                    payload.pop("max_completion_tokens", None)
                    payload["thinking"] = {"type": "disabled" if model.reasoning_effort == "none" else "enabled"}
                    payload["reasoning_effort"] = model.reasoning_effort
                    payload["stream_options"] = {"include_usage": True}
                    # OpenCode tool-result parts can be emitted as text arrays.
                    for message in payload["messages"]:
                        if isinstance(message.get("content"), list):
                            if any(p.get("type") != "text" for p in message["content"]):
                                raise StopRun("unsupported_input")
                            message["content"] = "\n".join(p["text"] for p in message["content"])
                else:
                    payload["thinking"] = {"type": "adaptive"}
                    payload["output_config"] = {"effort": model.reasoning_effort}
                    payload.setdefault("system", "")
                    payload.setdefault("tools", [])
            encoded = json.dumps(payload, ensure_ascii=False).encode()
            if len(encoded) > self.limits.max_request_bytes:
                raise StopRun("request_size_limit")
            count = None
            if model.token_counting == "model":
                count = provider.count_input_tokens(payload, min(self.remaining(), self.limits.token_count_timeout_seconds))
                estimate = count + self.limits.token_count_margin
            else:
                # A transparent gateway has no Provider.accept token allowance
                # for encrypted history: conservatively count its bytes too.
                estimate = len(encoded) + 2048
            reservation = self.ledger.reserve(model, len(encoded), estimate)
            index = self.ledger.calls
            save_json(self.directory / "calls" / f"{index:03d}-request.json", payload)
            self.recorder.event("request_started", call=index, model_id=model.id, turn=self.turn, primary_role=self.active_role,
                                request_bytes=len(encoded), estimated_input_tokens=estimate,
                                estimated_reserve_usd=str(reservation))
            try:
                body, raw = forward_stream(provider, payload, min(self.remaining(), self.limits.request_timeout_seconds))
                save_json(self.directory / "calls" / f"{index:03d}-response.json", raw)
                (self.directory / "calls" / f"{index:03d}-response.sse").write_bytes(body)
                usage = provider.usage(raw)
            except Exception:
                self.ledger.mark_unknown(reservation)
                self.recorder.event("usage_unknown", call=index, estimated_reserve_usd=str(reservation))
                self.halted = "usage_unknown"
                raise StopRun("usage_unknown") from None
            entry = self.ledger.record(model, usage, raw.get("id", ""), raw.get("model", model.model))
            self.recorder.event("request_completed", **entry, turn=self.turn, primary_role=self.active_role)
            if count is not None:
                self.recorder.event("input_count_comparison", call=index, counted_input_tokens=count,
                                    reported_input_tokens=usage.input_tokens, reserved_input_tokens=estimate)
            self.ledger.check_observed_limits()
            if ((model.provider == "deepseek" and raw["choices"][0]["finish_reason"] == "length")
                    or (model.provider == "openai" and raw.get("status") != "completed")
                    or (model.provider == "anthropic" and raw.get("stop_reason") == "max_tokens")):
                raise StopRun("output_token_limit" if usage.output_tokens >= model.max_output_tokens else "incomplete_model_response")
            # Admit all tools, including OpenCode's native subagent handoffs,
            # before releasing model output. MCP execution is not counted twice.
            for _ in range(raw.get("_lab_tool_calls", 0)):
                self.ledger.tool_step()
            self.remaining()
            return body

    def mcp(self, role, message):
        method = message.get("method")
        if method == "initialize":
            return {"protocolVersion": message["params"]["protocolVersion"], "capabilities": {"tools": {}},
                    "serverInfo": {"name": "agent-lab", "version": "1.0"}}
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": [{"name": t["name"], "description": t["description"], "inputSchema": t["parameters"]}
                              for t in role_tool_definitions(role)]}
        if method != "tools/call":
            raise ValueError("Unsupported MCP method")
        with self.lock:
            self.guard()
            if self.active_role is not None and role != self.active_role:
                raise StopRun("inactive_agent")
            params = message["params"]
            call = ToolCall(str(message.get("id", "")), params["name"], params.get("arguments", {}))
            if call.name == "request_clarification":
                self.recorder.event("clarification_requested", turn=self.turn, role=role,
                                    question=str(call.arguments.get("question", ""))[:2000])
                raise StopRun("needs_user_input")
            try:
                if call.name == "write_file" and (not self.allow_write or role == "planner"):
                    raise ValueError("Writes are disabled for this turn/role")
                result = execute(call, self.workspace, self.checks, self.remaining())
                self.workspace.verify_immutable()
            except (ValueError, OSError) as exc:
                result = {"ok": False, "error": str(exc)[:500]}
            self.recorder.event("tool", tool=call.name, arguments=call.arguments, result=result, turn=self.turn, role=role)
            return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                    "isError": not result.get("ok", False)}


@contextmanager
def serve_gateway(gateway):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, body=b"", content_type="application/json"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            self.reply(405)

        def do_POST(self):
            parts = self.path.strip("/").split("/")
            if not parts or not secrets.compare_digest(parts[0], gateway.secret):
                return self.reply(403)
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= gateway.limits.max_request_bytes:
                    raise StopRun("request_size_limit")
                payload = json.loads(self.rfile.read(size))
                if len(parts) == 3 and parts[1] == "mcp" and parts[2] in {"solo", "planner", "worker"}:
                    if "id" not in payload:
                        return self.reply(202)
                    result = gateway.mcp(parts[2], payload)
                    return self.reply(200, json.dumps({"jsonrpc": "2.0", "id": payload["id"], "result": result}, ensure_ascii=False).encode())
                if len(parts) >= 4 and parts[1] == "provider":
                    body = gateway.generation(parts[2], "/".join(parts[3:]), payload)
                    return self.reply(200, body, "text/event-stream")
                self.reply(404)
            except (StopRun, TokenCountError) as exc:
                reason = exc.reason if isinstance(exc, StopRun) else "input_count_error"
                with gateway.lock:
                    gateway.halted = gateway.halted or reason
                    gateway.recorder.event("gateway_stopped", reason=gateway.halted)
                self.reply(400, json.dumps({"error": {"message": reason, "type": "lab_stop"}}).encode())
            except Exception as exc:
                with gateway.lock:
                    gateway.halted = gateway.halted or "gateway_error"
                    gateway.recorder.event("gateway_error", exception_type=type(exc).__name__)
                self.reply(400, b'{"error":{"message":"Lab gateway failed","type":"lab_stop"}}')

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = False
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/{gateway.secret}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
