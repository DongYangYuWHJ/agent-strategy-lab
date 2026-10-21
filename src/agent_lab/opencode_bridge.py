"""OpenCode V2 launch helpers; credentials stay in the child process environment."""
import json
import base64
import os
from pathlib import Path
import shutil
import subprocess
from contextlib import contextmanager
import socket
import tempfile
import time
import re
import urllib.error
import urllib.parse
import urllib.request
from .settings import KEY_NAMES, resolve_credential

ROOT = Path(__file__).resolve().parents[2]
SUPPORTED_VERSION = "2.0.32"


def executable():
    command = shutil.which("opencode") or shutil.which("opencode.cmd")
    if not command:
        raise ValueError("OpenCode is not on PATH; install @opencode/cli 2.0.32 and reopen the terminal")
    path = Path(command)
    if path.suffix.lower() in {".cmd", ".ps1", ".bat"}:
        native = path.parent / "node_modules" / "@opencode" / "cli" / "bin" / "opencode.exe"
        if not native.is_file():
            raise ValueError("Cannot locate the native OpenCode binary behind the npm launcher")
        path = native
    return str(path)


def environment(required=()):
    result = dict(os.environ)
    for name in KEY_NAMES.values():
        result.pop(name, None)
    for provider in required:
        key, _ = resolve_credential(provider)
        if not key:
            raise ValueError(f"Configure the {provider} API key in settings.local.json or its environment variable")
        result[KEY_NAMES[provider]] = key
    return result


def redact(text, env):
    for name in KEY_NAMES.values():
        if env.get(name):
            text = text.replace(env[name], "[REDACTED]")
    return re.sub(r"(server password\s+)\S+", r"\1[REDACTED]", text)


def invoke(args, cwd=ROOT, required=(), timeout=30):
    env = environment(required)
    result = subprocess.run([executable(), *args], cwd=cwd, env=env, capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False)
    return result.returncode, redact(result.stdout, env), redact(result.stderr, env)


def api(url, path, timeout=5, password=None):
    headers = {}
    if password:
        headers["Authorization"] = "Basic " + base64.b64encode(("opencode:" + password).encode()).decode()
    request = urllib.request.Request(url + path, headers=headers)
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=timeout) as response:
        return json.load(response)


@contextmanager
def private_server(cwd=ROOT, required=()):
    env = environment(required)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    with tempfile.TemporaryFile() as logs:
        process = subprocess.Popen([executable(), "serve", "--hostname", "127.0.0.1", "--port", str(port)],
                                   cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=logs, stderr=logs,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            deadline = time.monotonic() + 30
            last_error = ""
            password = None
            while time.monotonic() < deadline:
                try:
                    logs.seek(0)
                    output = logs.read(20000).decode("utf-8", "replace")
                    match = re.search(r"server password\s+(\S+)", output)
                    if match:
                        password = match[1]
                    api(url, "/api/info", timeout=1, password=password)
                    break
                except (urllib.error.URLError, TimeoutError) as exc:
                    last_error = str(exc)
                    if process.poll() is not None:
                        logs.seek(0)
                        raise ValueError("OpenCode server exited: " + redact(logs.read().decode("utf-8", "replace"), env)[:1000]) from None
                    time.sleep(0.2)
            else:
                logs.seek(0)
                detail = redact(logs.read(20000).decode("utf-8", "replace"), env)
                raise ValueError("OpenCode private server not ready: " + last_error + " / " + detail[-2000:])
            yield url, env, password
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


def check_version():
    code, output, error = invoke(["--version"])
    if code or output.strip() != "opencode v" + SUPPORTED_VERSION:
        raise ValueError("This integration requires OpenCode 2.0.32; observed: " + (output or error)[:200])
    return output.strip()


def launch():
    """Start an interactive terminal; do not submit an initial model prompt."""
    check_version()
    env = environment(("openai", "deepseek"))
    return subprocess.call([executable(), "--standalone"], cwd=ROOT, env=env)


def validate_agents(agents):
    expected = {
        "lab-coordinator": ("primary", "openai", "gpt-6.1-sol"),
        "lab-worker": ("subagent", "deepseek", "deepseek-flash"),
        "lab-solo": ("primary", "openai", "gpt-6.1-sol"),
    }
    found = {agent.get("id"): agent for agent in agents}
    for name, (mode, provider, model) in expected.items():
        agent = found.get(name, {})
        ref = agent.get("model") or {}
        if (agent.get("mode"), ref.get("providerID"), ref.get("id")) != (mode, provider, model):
            raise ValueError(f"OpenCode role missing or overridden: {name}; check higher-priority configuration")
    return [found[name] for name in expected]


def doctor():
    output = check_version()
    print(output.strip())
    code, output, error = invoke(["models", "--standalone"], required=("openai", "deepseek"), timeout=60)
    if code:
        raise ValueError("OpenCode model discovery failed: " + error[:500])
    # Print only candidate identifiers, never provider configuration or credentials.
    selected = [line for line in output.splitlines() if any(name in line for name in ("gpt-6.1-sol", "gpt-6-luna", "deepseek-flash"))]
    print("Candidate models:", "\n".join(selected) or "No matching catalog entries")
    with private_server(required=("openai", "deepseek")) as (url, env, password):
        query = urllib.parse.urlencode({"location.directory": str(ROOT)})
        deadline = time.monotonic() + 20
        while True:
            payload = api(url, "/api/agent?" + query, password=password)
            agents = payload.get("data", [])
            if all(any(agent.get("id") == name for agent in agents)
                   for name in ("lab-coordinator", "lab-worker", "lab-solo")) or time.monotonic() >= deadline:
                break
            time.sleep(0.2)
        selected_agents = validate_agents(agents)
        print("Project agents:", json.dumps([{key: agent.get(key) for key in ("id", "mode", "model")}
                                             for agent in selected_agents], ensure_ascii=False))
    print("Configuration verified. No task submitted; API authentication and task execution remain untested here.")
