"""OpenCode-backed, bounded multi-turn experiments using the shared task graders."""
from contextlib import contextmanager
from copy import deepcopy
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
from .opencode_permissions import (PermissionConfigurationError, PERMISSION_POLICY_VERSION,
                                   ROLE_AGENT_IDS, role_ids, role_permissions,
                                   audit_registered_agents, permission_probes)
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


def model_matches(actual, model):
    return (isinstance(actual, dict) and all(actual.get(k) == v for k, v in model_ref(model).items())
            and actual.get("variant") in (None, "default"))


def workflow_role_prompts(strategy):
    if strategy == "single_agent":
        return {"solo": SYSTEM + "\nDo not delegate."}
    if strategy not in {"planner_worker", "planner_handoff"}:
        raise ValueError("Unsupported workflow strategy")
    root = Path(__file__).resolve().parents[2] / "roles"
    if strategy == "planner_handoff":
        names = (("planner", "workflow-handoff-planner.md"), ("worker", "workflow-handoff-executor.md"))
    else:
        names = (("planner", "workflow-planner.md"), ("worker", "workflow-executor.md"))
    return {role: SYSTEM + "\n" + (root / name).read_text(encoding="utf-8")
                    .replace("{{EXECUTOR_AGENT_ID}}", ROLE_AGENT_IDS["worker"])
                    .replace("{{PLANNER_AGENT_ID}}", ROLE_AGENT_IDS["planner"])
            for role, name in names}


def opencode_config(models, gateway_url, limits, strategy, role_prompts=None):
    role_prompts = workflow_role_prompts(strategy) if role_prompts is None else role_prompts
    providers = {}
    packages = {"deepseek": "openai-compatible", "openai": "openai/responses", "anthropic": "anthropic"}
    for model in models:
        entry = {"modelID": model.model, "name": model.id,
                 "limit": {"context": 1048576 if model.provider == "deepseek" and model.max_output_tokens is None else 100000,
                           "input": limits.max_estimated_input_tokens, "output": model.output_reserve_tokens},
                 "capabilities": {"tools": True, "input": ["text"], "output": ["text"],
                                  "reasoning": {"supported": model.reasoning_effort != "none"}}}
        if model.provider == "deepseek":
            entry["compatibility"] = {"reasoningField": "reasoning_content"}
        providers["lab-" + model.id] = {"name": "Lab " + model.id,
            "package": "@opencode/ai/providers/" + packages[model.provider],
            "settings": {"apiKey": "local-gateway", "baseURL": gateway_url + "/provider/" + model.id,
                         "timeout": (limits.request_timeout_seconds + 10) * 1000, "encoding": "none"},
            "models": {model.id: entry}}
    ids = role_ids(strategy)
    main = ids["solo"] if strategy == "single_agent" else ids["planner"]
    def agent(role, model, mode):
        permissions = role_permissions(role, strategy)
        return {"description": "Bounded workflow " + role, "mode": mode, "model": "lab-" + model.id + "/" + model.id,
                "system": role_prompts[role],
                "steps": limits.max_calls, "permissions": permissions}
    executor_mode = "primary" if strategy == "planner_handoff" else "subagent"
    agents = ({main: agent("solo", models[0], "primary")} if strategy == "single_agent" else
              {main: agent("planner", models[0], "primary"), ids["worker"]: agent("worker", models[1], executor_mode)})
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
        ids = role_ids(strategy)
        self.main = ids["solo"] if strategy == "single_agent" else ids["planner"]
        query = urllib.parse.urlencode({"location.directory": str(workspace.root)})
        deadline = time.monotonic() + 15
        while True:
            agents = request(url, "/api/agent?" + query, password)["data"]
            if all(any(a.get("id") == name for a in agents) for name in ids.values()):
                break
            if time.monotonic() >= deadline:
                save_json(directory / "registered-agents.json", agents)
                save_json(directory / "permission-audit.json", {"passed": False,
                          "policy": PERMISSION_POLICY_VERSION, "error": "Experiment roles did not load"})
                raise PermissionConfigurationError("Workflow role configuration did not load")
            time.sleep(0.15)
        save_json(directory / "registered-agents.json", agents)
        audit = {"schema_version": 1, "policy": PERMISSION_POLICY_VERSION, "passed": False, "probes": []}
        save_json(directory / "permission-audit.json", audit)
        try:
            expected = json.loads((directory / "opencode-config.json").read_text(encoding="utf-8"))
            audit["registered_roles"] = audit_registered_agents(agents, {"roles": ids, "agents": expected["agents"], "strategy": strategy})
        except PermissionConfigurationError as exc:
            audit["error"] = str(exc)
            save_json(directory / "permission-audit.json", audit)
            raise
        result = request(url, "/api/session", password,
                         {"title": "Agent Lab workflow", "agent": self.main, "model": model_ref(models[0]),
                          "location": {"directory": str(workspace.root)}})
        self.id = result["data"]["id"]
        save_json(directory / "session.json", result)
        try:
            for role, name in ids.items():
                for probe in permission_probes(role, strategy):
                    reply = self.call("/permission", {"agent": name, "action": probe["action"], "resources": probe["resources"]})
                    effect = (reply or {}).get("data", {}).get("effect")
                    audit["probes"].append({"agent": name, **probe, "observed": effect})
                    save_json(directory / "permission-audit.json", audit)
                    if effect != probe["expected"]:
                        raise PermissionConfigurationError(f"Effective permission mismatch: {name}: {probe['action']}")
            if gateway.ledger.calls:
                raise PermissionConfigurationError("Generation occurred before permission audit completed")
            audit["passed"] = True
            save_json(directory / "permission-audit.json", audit)
            gateway.recorder.event("permission_audit_passed", roles=ids, probes=len(audit["probes"]))
        except Exception as exc:
            audit["error"] = str(exc)[:1200]
            save_json(directory / "permission-audit.json", audit)
            if isinstance(exc, PermissionConfigurationError):
                raise
            raise PermissionConfigurationError("OpenCode effective permission audit could not complete") from exc

    def call(self, suffix, payload=None, method=None, timeout=10):
        return request(self.url, "/api/session/" + self.id + suffix, self.password, payload, method, timeout)

    def select_primary(self, role, model, turn_dir):
        """Switch an idle existing session, then read back its effective selection."""
        target = ROLE_AGENT_IDS[role]
        evidence = {"session_id": self.id, "role": role, "expected_agent": target,
                    "expected_model": model_ref(model), "passed": False}
        try:
            active = request(self.url, "/api/session/active", self.password).get("data", {})
            if self.id in active or self.call("/inbox").get("data", []):
                raise ValueError("Cannot switch a busy session")
            before = self.call("")["data"]
            evidence["before"] = before
            if before.get("agent") != target:
                self.call("/agent", {"agent": target})
            if not model_matches(before.get("model"), model):
                self.call("/model", {"model": model_ref(model)})
            after = self.call("")["data"]
            evidence["after"] = after
            if after.get("id") != self.id or after.get("agent") != target or not model_matches(after.get("model"), model):
                raise ValueError("Session selection did not match the requested agent and model")
            evidence["passed"] = True
            self.main = target
            self.gateway.recorder.event("primary_selected", session_id=self.id, role=role,
                                        agent=target, model_id=model.id, turn=self.gateway.turn)
        except Exception as exc:
            evidence["error"] = str(exc)[:1000]
            raise StopRun("agent_switch_error") from exc
        finally:
            save_json(turn_dir / "selection.json", evidence)

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


def run_workflow(task, models, limits, output, workflow, strategy="single_agent", session_factory=OpenCodeSession, role_prompts=None):
    if strategy not in {"single_agent", "planner_worker", "planner_handoff"} or len(models) != (1 if strategy == "single_agent" else 2):
        raise ValueError("Workflow architecture needs one solo model or planner and worker models")
    if strategy == "planner_handoff" and (len(workflow.turns) < 2 or workflow.turns[0].id != "plan" or workflow.turns[0].allow_write):
        raise ValueError("Planner handoff requires a read-only first plan turn and later executor turns")
    if any(m.provider == "mock" for m in models):
        raise ValueError("OpenCode workflows require real provider configurations")
    role_prompts = workflow_role_prompts(strategy) if role_prompts is None else role_prompts
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
        "token_policy": {m.id: {"max_output_tokens": m.max_output_tokens,
                               "enforce_total_token_limit": m.enforce_total_token_limit,
                               "output_reserve_tokens": m.output_reserve_tokens} for m in models},
        "system_prompt": SYSTEM, "role_prompts": role_prompts, "execution_kind": "live",
        "agent_ids": role_ids(strategy), "permission_policy": PERMISSION_POLICY_VERSION,
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
            config = opencode_config(models, gateway_url, limits, strategy, role_prompts)
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
                        if strategy == "planner_handoff":
                            role = "planner" if index == 0 else "worker"
                            model = models[0 if index == 0 else 1]
                            # Selection is verified while the generation gate is closed.
                            with gateway.lock:
                                gateway.turn = turn.id
                                gateway.active_role = role
                                gateway.active_model_id = model.id
                            session.select_primary(role, model, turn_dir)
                        text = (json.dumps(task.public_contract(), ensure_ascii=False) + "\n\n" if index == 0 else "") + turn.prompt
                        with gateway.lock:
                            gateway.turn, gateway.allow_write, gateway.closed = turn.id, turn.allow_write, False
                            before_calls = gateway.ledger.calls
                        item = {"index": index, "id": turn.id, "prompt": text, "allow_write": turn.allow_write,
                                "started_at": now(), "status": "running"}
                        if strategy == "planner_handoff":
                            item.update(primary_role=role, agent_id=ROLE_AGENT_IDS[role], model_id=gateway.active_model_id)
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
                                        accounting_cumulative=deepcopy(gateway.ledger.summary()))
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
    except PermissionConfigurationError as exc:
        status, reason = "error", "permission_configuration_error"
        recorder.event("permission_audit_failed", message=str(exc))
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
