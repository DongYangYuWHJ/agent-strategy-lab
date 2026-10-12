"""Local credentials, kept separate from frozen experimental configuration."""
import json
import os
from pathlib import Path


LOCAL_SETTINGS = Path(__file__).resolve().parents[2] / "settings.local.json"
KEY_NAMES = {"openai": "OPENAI_API_KEY", "deepseek": "DEEPSEEK_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}


def checked_key(value):
    if not isinstance(value, str):
        raise ValueError("API keys must be strings; leave unused keys empty")
    key = value.strip()
    if len(key) > 4096 or any(not 33 <= ord(char) <= 126 for char in key):
        raise ValueError("API key contains invalid characters or exceeds the length limit")
    return key


def local_credentials(path):
    try:
        with path.open("rb") as source:
            data = source.read(16385)
    except FileNotFoundError:
        return {}
    except OSError:
        raise ValueError("Cannot read settings.local.json") from None
    if len(data) > 16384:
        raise ValueError("settings.local.json exceeds the size limit")
    try:
        raw = json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        # Parser errors can quote private file contents; expose only a fixed message.
        raise ValueError("settings.local.json must contain valid UTF-8 JSON") from None
    if (not isinstance(raw, dict) or set(raw) != {"schema_version", "providers"}
            or type(raw["schema_version"]) is not int or raw["schema_version"] != 1
            or not isinstance(raw["providers"], dict) or not set(raw["providers"]) <= set(KEY_NAMES)):
        raise ValueError("settings.local.json requires schema_version=1 and providers: openai/deepseek/anthropic")
    keys = {}
    for name, config in raw["providers"].items():
        if not isinstance(config, dict) or set(config) != {"api_key"}:
            raise ValueError("Each settings provider must contain only api_key")
        keys[name] = checked_key(config["api_key"])
    return keys


def resolve_credential(provider, path=None):
    """Return a private key and a non-secret source label, without changing os.environ."""
    if provider not in KEY_NAMES:
        raise ValueError("Unsupported credential provider")
    key = checked_key(os.environ.get(KEY_NAMES[provider], ""))
    if key:
        return key, "environment"
    key = local_credentials(Path(path) if path is not None else LOCAL_SETTINGS).get(provider, "")
    return (key, "local_file") if key else ("", "missing")


def require_credential(provider):
    key, _ = resolve_credential(provider)
    if not key:
        raise ValueError(f"Configure {KEY_NAMES[provider]} or the {provider} api_key in settings.local.json before running")
    return key
