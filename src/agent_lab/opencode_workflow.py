"""OpenCode-backed, bounded multi-turn experiments using the shared task graders."""
from contextlib import contextmanager
from dataclasses import asdict
import base64
import json
from pathlib import Path
import re
import shutil
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from .accounting import StopRun
from .domain import digest, now, save_json
from .evaluation import Checks
from .opencode_bridge import executable, environment, SUPPORTED_VERSION
from .runner import task_fingerprint
from .telemetry import Recorder
from .workflow_gateway import Gateway, serve_gateway
from .workflows import SYSTEM
from .workspace import Workspace, file_hash, inventory


def request(url, path, password, payload=None, method=None, timeout=10):
    headers = {"Authorization": "Basic " + base64.b64encode(("opencode:" + password).encode()).decode()}
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=timeout) as response:
            body = response.read(32 * 1024 * 1024 + 1)
            if len(body) > 32 * 1024 * 1024:
                raise ValueError("OpenCode response too large")
            return json.loads(body) if body else None
    except urllib.error.HTTPError as exc:
        # Local server errors cannot include upstream credentials; retain bounded diagnostics.
        detail = exc.read(1000).decode("utf-8", "replace")
        raise ValueError(f"OpenCode API {path}: HTTP {exc.code}: {detail}") from None


@contextmanager
def isolated_server(directory, cwd):
    env = environment(())  # Only the parent gateway holds upstream keys.
    runtime = directory / "opencode-runtime"
    for key, name in (("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"),
                      ("XDG_STATE_HOME", "state"), ("XDG_CACHE_HOME", "cache"),
                      ("TEMP", "temp"), ("TMP", "temp")):
        path = runtime / name
        path.mkdir(parents=True, exist_ok=True)
        env[key] = str(path)
    # Never inherit launch overrides from an unrelated interactive configuration.
    for key in list(env):
        if key.startswith("OPENCODE_"):
            del env[key]
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    logs = (directory / "opencode-server.log").open("w+b")
    process = subprocess.Popen([executable(), "serve", "--hostname", "127.0.0.1", "--port", str(port)],
        cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=logs, stderr=logs,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        deadline = time.monotonic() + 30
        password = ""
        while time.monotonic() < deadline:
            logs.seek(0)
            output = logs.read(30000).decode("utf-8", "replace")
            match = re.search(r"server password\s+(\S+)", output)
            if match:
                password = match[1]
            try:
                info = request(url, "/api/info", password, timeout=1)
                if info.get("version") not in {SUPPORTED_VERSION, "v" + SUPPORTED_VERSION}:
                    raise ValueError("Workflow integration requires OpenCode " + SUPPORTED_VERSION)
                break
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                if process.poll() is not None:
                    raise ValueError("OpenCode server exited before becoming ready") from None
                time.sleep(0.1)
            except ValueError as exc:
                if "/api/info: HTTP 401" not in str(exc):
                    raise
                time.sleep(0.1)
        else:
            raise ValueError("OpenCode server readiness timed out")
        yield url, password
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        logs.close()


def model_ref(model):
    return {"providerID": "lab-" + model.id, "id": model.id}


def opencode_config(models, gateway_url, limits, strategy):
    providers = {}
    packages = {"deepseek": "openai-compatible", "openai": "openai/responses", "anthropic": "anthropic"}
    for model in models:
        entry = {"modelID": model.model, "name": model.id,
                 "limit": {"context": 100000, "input": limits.max_estimated_input_tokens, "output": model.max_output_tokens},
                 "capabilities": {"tools": True, "input": ["text"], "output": ["text"],
                                  "reasoning": {"supported": model.reasoning_effort != "none"}}}
        if model.provider == "deepseek":
            entry["compatibility"] = {"reasoningField": "reasoning_content"}
        providers["lab-" + model.id] = {"name": "Lab " + model.id,
            "package": "@opencode/ai/providers/" + packages[model.provider],
            "settings": {"apiKey": "local-gateway", "baseURL": gateway_url + "/provider/" + model.id,
                         "timeout": (limits.request_timeout_seconds + 10) * 1000, "encoding": "none"},
            "models": {model.id: entry}}
    main = "lab-solo" if strategy == "single_agent" else "lab-planner"
    def agent(role, model, mode):
        permissions = [{"action": "lab_" + role + "_*", "resource": "*", "effect": "allow"}]
        if role == "planner":
            permissions.append({"action": "subagent", "resource": "lab-worker", "effect": "allow"})
        return {"description": "Bounded workflow " + role, "mode": mode, "model": "lab-" + model.id + "/" + model.id,
                "system": SYSTEM + ("\nCoordinate lab-worker. Do not edit files yourself. Pass all relevant requirements and current turn constraints."
                                    if role == "planner" else "\nDo not delegate."),
                "steps": limits.max_calls, "permissions": permissions}
    agents = ({main: agent("solo", models[0], "primary")} if strategy == "single_agent" else
              {main: agent("planner", models[0], "primary"), "lab-worker": agent("worker", models[1], "subagent")})
    roles = ["solo"] if strategy == "single_agent" else ["planner", "worker"]
    return {"model": "lab-" + models[0].id + "/" + models[0].id, "default_agent": main,
            "snapshots": False, "compaction": {"auto": False},
            "permissions": [{"action": "*", "resource": "*", "effect": "deny"}],
            "policies": [{"action": "provider.use", "resource": "*", "effect": "deny"},
                         *[{"action": "provider.use", "resource": name, "effect": "allow"} for name in providers]],
            "agents": agents, "providers": providers,
            "mcp": {"servers": {"lab_" + role: {"type": "remote", "url": gateway_url + "/mcp/" + role,
                "oauth": False, "codemode": False,
                "timeout": {"startup": 10000, "catalog": 10000, "execution": (limits.check_timeout_seconds + 10) * 1000}}
                for role in roles}}}


class OpenCodeSession:
    def __init__(self, url, password, workspace, directory, models, strategy, gateway):
        self.url, self.password, self.workspace = url, password, workspace
        self.directory, self.gateway = directory, gateway
        self.main = "lab-solo" if strategy == "single_agent" else "lab-planner"
        query = urllib.parse.urlencode({"location.directory": str(workspace.root)})
        deadline = time.monotonic() + 15
        while True:
            agents = request(url, "/api/agent?" + query, password)["data"]
            actual = next((a for a in agents if a.get("id") == self.main), None)
            if actual and actual.get("model") == model_ref(models[0]):
                break
            if time.monotonic() >= deadline:
                save_json(directory / "registered-agents.json", agents)
                raise ValueError("Workflow role configuration did not load")
            time.sleep(0.15)
        save_json(directory / "registered-agents.json", agents)
        result = request(url, "/api/session", password,
                         {"title": "Agent Lab workflow", "agent": self.main, "model": model_ref(models[0]),
                          "location": {"directory": str(workspace.root)}})
        self.id = result["data"]["id"]
        save_json(directory / "session.json", result)

    def call(self, suffix, payload=None, method=None, timeout=10):
        return request(self.url, "/api/session/" + self.id + suffix, self.password, payload, method, timeout)

    def run_turn(self, text, turn_dir):
        before = self.gateway.ledger.calls
        admitted = self.call("/prompt", {"text": text})
        save_json(turn_dir / "admission.json", admitted)
        # A prompt admission response is not completion. Wait for an actual
        # assistant message and for the foreground main drain to become idle.
        while True:
            self.gateway.remaining()
            if self.gateway.halted:
                raise StopRun(self.gateway.halted)
            forms = self.call("/form")
            data = forms.get("data", [])
            if data:
                save_json(turn_dir / "pending-forms.json", forms)
                raise StopRun("needs_user_input")
            active = request(self.url, "/api/session/active", self.password).get("data", {})
            if self.id not in active:
                inbox = self.call("/inbox").get("data", [])
                if not inbox:
                    messages = self.call("/message?limit=100")
                    save_json(turn_dir / "messages.json", messages)
                    if completed_turn(messages, admitted):
                        if self.gateway.ledger.calls <= before:
                            raise StopRun("no_model_response")
                        return messages
            time.sleep(0.15)

    def close(self):
        try:
            self.call("/interrupt", {}, timeout=3)
        except Exception:
            pass
        try:
            exported = request(self.url, "/api/experimental/session/" + self.id + "/export", self.password)
            save_json(self.directory / "session-export.json", exported)
            children = request(self.url, "/api/session?" + urllib.parse.urlencode({"parentID": self.id, "limit": 100}), self.password)
            save_json(self.directory / "child-sessions.json", children)
            for child in children.get("data", []):
                data = request(self.url, "/api/experimental/session/" + child["id"] + "/export", self.password)
                save_json(self.directory / "children" / (child["id"] + ".json"), data)
        except Exception as exc:
            self.gateway.recorder.event("session_export_error", exception_type=type(exc).__name__)


def completed_turn(messages, admitted):
    """Use the main session's terminal event for this input, never answer wording."""
    created = admitted["data"]["time"]["created"]
    rows = [m for m in messages.get("data", []) if m.get("time", {}).get("created", 0) >= created]
    idle = next((m for m in rows if m.get("type") == "idle"), None)
    if idle is None:
        return False
    if idle.get("outcome") != "succeeded" or any(m.get("type") == "error" for m in rows):
        raise StopRun("opencode_session_error")
    return any(m.get("type") == "assistant" and m.get("time", {}).get("completed") for m in rows)


def run_workflow(task, models, limits, output, workflow, strategy="single_agent", session_factory=OpenCodeSession):
    if strategy not in {"single_agent", "planner_worker"} or len(models) != (1 if strategy == "single_agent" else 2):
        raise ValueError("Workflow architecture needs one solo model or planner and worker models")
    if any(m.provider == "mock" for m in models):
        raise ValueError("OpenCode workflows require real provider configurations")
    directory = output.resolve() / (task.id + "-" + "--".join(m.id for m in models) + "-" + uuid.uuid4().hex[:12])
    directory.mkdir(parents=True, exist_ok=False)
    recorder = Recorder(directory)
    workspace = Workspace(task, directory)
    checks = Checks(task, directory, workspace, limits.check_timeout_seconds)
    gateway = Gateway(task, models, limits, directory, recorder, workspace, checks)
    started_at = now()
    started = time.monotonic()
    configuration = {"schema_version": 1, "framework_fingerprint": digest(inventory(Path(__file__).parent)),
        "backend": "opencode", "opencode_version": SUPPORTED_VERSION,
        "task": task.public_contract(), "task_fingerprint": task_fingerprint(task),
        "model": asdict(models[0]), "models": [asdict(m) for m in models],
        "limits": asdict(limits), "strategy": {"name": strategy, "version": 1}, "workflow": asdict(workflow),
        "system_prompt": SYSTEM, "execution_kind": "live",
        "token_counting": {m.id: gateway.clients[m.id].token_counting_info() for m in models}}
    save_json(directory / "config.json", configuration)
    save_json(directory / "task.json", task.public_contract())
    turns = []
    status, reason, final_evidence = "running", "", None
    def state(phase):
        recorder.snapshot({"schema_version": 1, "run_id": directory.name, "status": status,
                           "phase": phase, "turn": gateway.turn, "started_at": started_at,
                           "updated_at": now(), "accounting": gateway.ledger.summary()})
        recorder.event("phase", phase=phase, turn=gateway.turn)
    try:
        with serve_gateway(gateway) as gateway_url:
            config = opencode_config(models, gateway_url, limits, strategy)
            config_path = workspace.root / "opencode.jsonc"
            if config_path.exists():
                raise ValueError("Task source must not contain the reserved opencode.jsonc control file")
            save_json(config_path, config)
            # Immutable control file: invisible to task MCP, protected from edits.
            workspace.original["opencode.jsonc"] = file_hash(config_path)
            shutil.copyfile(config_path, workspace.baseline / "opencode.jsonc")
            save_json(directory / "opencode-config.json", config)
            with isolated_server(directory, workspace.root) as (url, password):
                session = session_factory(url, password, workspace, directory, models, strategy, gateway)
                try:
                    for index, turn in enumerate(workflow.turns):
                        gateway.remaining()
                        turn_dir = directory / "turns" / f"{index:02d}-{turn.id}"
                        turn_dir.mkdir(parents=True)
                        text = (json.dumps(task.public_contract(), ensure_ascii=False) + "\n\n" if index == 0 else "") + turn.prompt
                        with gateway.lock:
                            gateway.turn, gateway.allow_write, gateway.closed = turn.id, turn.allow_write, False
                            before_calls = gateway.ledger.calls
                        item = {"index": index, "id": turn.id, "prompt": text, "allow_write": turn.allow_write,
                                "started_at": now(), "status": "running"}
                        turns.append(item)
                        save_json(turn_dir / "turn.json", item)
                        recorder.event("user_message", index=index, turn=turn.id, text=text)
                        state("waiting_for_turn")
                        session.run_turn(text, turn_dir)
                        with gateway.lock:
                            gateway.closed = True
                            workspace.verify_immutable()
                            snapshot = turn_dir / "workspace"
                            for name in workspace.list_files():
                                dest = snapshot / name
                                dest.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copyfile(workspace.resolve(name), dest)
                            item.update(status="completed", ended_at=now(),
                                        calls=gateway.ledger.calls - before_calls,
                                        accounting_cumulative=gateway.ledger.summary())
                        save_json(turn_dir / "turn.json", item)
                        recorder.event("turn_completed", turn=turn.id, index=index)
                        state("between_turns")
                    state("final_acceptance")
                    public = checks.run("public", gateway.remaining())
                    recorder.event("verification", kind="public", evidence=public)
                    final_evidence = checks.run("final", gateway.remaining())
                    recorder.event("verification", kind="final", evidence=final_evidence)
                    if not public["ok"] or not final_evidence["ok"]:
                        raise StopRun("check_timeout" if "timed_out" in {public["status"], final_evidence["status"]} else "environment_error")
                    status = "succeeded" if public["passed"] and final_evidence["passed"] else "failed"
                    reason = "accepted" if status == "succeeded" else "acceptance_failed"
                    save_json(directory / "delivery.json", {"public": public, "final": final_evidence})
                finally:
                    gateway.closed = True
                    session.close()
    except StopRun as exc:
        status, reason = "stopped", exc.reason
    except KeyboardInterrupt:
        status, reason = "cancelled", "interrupted"
    except Exception as exc:
        status, reason = "error", "environment_error"
        recorder.event("error", exception_type=type(exc).__name__, message=str(exc)[:1200])
    finally:
        gateway.closed = True
        if turns and turns[-1]["status"] == "running":
            turns[-1].update(status="stopped", stop_reason=reason, ended_at=now())
            save_json(directory / "turns" / f"{turns[-1]['index']:02d}-{turns[-1]['id']}" / "turn.json", turns[-1])
        workspace.export_diff(directory / "changes.patch")
    result = {"schema_version": 1, "run_id": directory.name, "task_id": task.id,
        "model_id": "--".join(m.id for m in models), "provider": "--".join(m.provider for m in models),
        "strategy": strategy, "backend": "opencode", "workflow_id": workflow.id, "execution_kind": "live",
        "status": status, "stop_reason": reason, "accepted": status == "succeeded", "repairs": 0,
        "started_at": started_at, "ended_at": now(), "duration_seconds": round(time.monotonic() - started, 6),
        "config_fingerprint": digest(configuration), "accounting": gateway.ledger.summary(),
        "turns": turns, "turns_completed": sum(t["status"] == "completed" for t in turns),
        "turns_expected": len(workflow.turns), "final_evidence": final_evidence, "artifact_dir": str(directory)}
    save_json(directory / "result.json", result)
    state("finished")
    recorder.event("run_finished", status=status, stop_reason=reason)
    return result
