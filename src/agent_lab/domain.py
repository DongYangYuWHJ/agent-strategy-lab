"""Versioned contracts shared by all strategies and providers."""
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re

SCHEMA_VERSION = 1


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def money(value) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite() or result < 0:
        raise ValueError("Money and prices must be finite and nonnegative")
    return result


def safe_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", value):
        raise ValueError(f"Invalid identifier: {value!r}")
    return value


def relative_path(value: str) -> str:
    path = Path(value)
    if not value or path.is_absolute() or path.drive or ".." in path.parts or "\\" in value or ":" in value:
        raise ValueError(f"Expected a relative path using forward slashes: {value!r}")
    if any(part.startswith(".") for part in path.parts):
        raise ValueError("Hidden paths are not available to agents")
    return path.as_posix()


@dataclass(frozen=True)
class Limits:
    max_calls: int = 12
    max_tool_steps: int = 30
    max_repairs: int = 2
    max_no_progress: int = 2
    max_total_tokens: int = 100000
    max_request_bytes: int = 1048576
    max_estimated_input_tokens: int = 64000
    max_seconds: int = 180
    request_timeout_seconds: int = 300
    token_count_timeout_seconds: int = 30
    token_count_margin: int = 256
    check_timeout_seconds: int = 15
    max_cost_usd: str = "2.00"

    def __post_init__(self):
        for name, value in asdict(self).items():
            if name == "max_cost_usd":
                money(value)
            elif type(value) is not int or value < (0 if name == "max_repairs" else 1):
                raise ValueError(f"Invalid limit: {name}")
        # Transport size and estimated model input are separate limits: encrypted
        # continuation state can be much larger than the tokens it represents.
        if self.max_request_bytes > 1048576:
            raise ValueError("max_request_bytes must be <= 1048576")
        if self.max_estimated_input_tokens > 64000:
            raise ValueError("max_estimated_input_tokens must be <= 64000; long-context pricing is not implemented")


@dataclass(frozen=True)
class Pricing:
    input: str
    output: str
    cached_input: str = "0"
    cache_write: str = "0"
    verified_on: str = ""
    source: str = ""

    def __post_init__(self):
        for value in (self.input, self.output, self.cached_input, self.cache_write):
            money(value)


@dataclass(frozen=True)
class Model:
    id: str
    provider: str
    model: str
    pricing: Pricing
    max_output_tokens: int = 4096
    reasoning_effort: str = "medium"
    mock_behavior: str = "pass"
    token_counting: str = "estimate"

    def __post_init__(self):
        safe_id(self.id)
        if self.provider not in {"mock", "openai", "deepseek", "anthropic"}:
            raise ValueError("Unsupported provider")
        if not self.model or type(self.max_output_tokens) is not int or not 16 <= self.max_output_tokens <= 32768:
            raise ValueError("Invalid model or output limit")
        if self.reasoning_effort not in {"none", "low", "medium", "high", "xhigh", "max"}:
            raise ValueError("Invalid reasoning_effort")
        if self.provider == "openai" and self.model in {"gpt-6-astra", "gpt-6.1-sol"} and self.reasoning_effort == "none":
            raise ValueError("This model does not support reasoning_effort=none")
        if self.provider == "anthropic" and self.reasoning_effort not in {"low", "medium", "high", "max"}:
            raise ValueError("Unsupported Anthropic effort")
        if self.provider == "deepseek" and self.reasoning_effort not in {"none", "low", "high", "max"}:
            raise ValueError("DeepSeek effort must be none, low, high, or max")
        if self.mock_behavior not in {"pass", "stuck", "invalid", "missing_usage"}:
            raise ValueError("Invalid mock behavior")
        if self.token_counting not in {"estimate", "model"}:
            raise ValueError("token_counting must be estimate or model")
        if self.provider == "mock" and self.token_counting != "estimate":
            raise ValueError("Mock providers only support estimated token counts")


def load_models(path: Path) -> dict[str, Model]:
    raw = read_json(path)
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported model catalog schema")
    result = {}
    for item in raw["models"]:
        item = dict(item)
        item["pricing"] = Pricing(**item["pricing"])
        model = Model(**item)
        if model.id in result:
            raise ValueError("Duplicate model ID")
        result[model.id] = model
    return result


@dataclass(frozen=True)
class Task:
    id: str
    description: str
    acceptance: list[str]
    source_dir: Path
    editable_files: list[str]
    public_check: Path
    final_check: Path
    manifest_path: Path

    @classmethod
    def load(cls, path: Path):
        path = path.resolve()
        raw = read_json(path)
        if raw.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("Unsupported task schema")
        root = path.parent
        def local(value):
            candidate = root / relative_path(value)
            if candidate.is_symlink() or not candidate.resolve().is_relative_to(root):
                raise ValueError("Task paths cannot escape the task directory")
            return candidate.resolve()
        task = cls(safe_id(raw["id"]), raw["description"], raw["acceptance"],
                   local(raw["source_dir"]), [relative_path(p) for p in raw["editable_files"]],
                   local(raw["public_check"]), local(raw["final_check"]), path)
        if (not isinstance(task.description, str) or not task.description
                or not isinstance(task.acceptance, list) or not task.acceptance
                or any(not isinstance(item, str) or not item for item in task.acceptance)
                or not task.editable_files):
            raise ValueError("Task description, acceptance, and editable files are required")
        if not task.source_dir.is_dir() or not task.public_check.is_file() or not task.final_check.is_file():
            raise ValueError("Task source or checks are missing")
        if task.public_check.is_relative_to(task.source_dir) or task.final_check.is_relative_to(task.source_dir):
            raise ValueError("Trusted checks must live outside the editable source")
        return task

    def public_contract(self):
        return {"schema_version": SCHEMA_VERSION, "id": self.id, "description": self.description,
                "acceptance": self.acceptance, "editable_files": self.editable_files}


@dataclass(frozen=True)
class Plan:
    """Reserved handoff contract; v1 executes single_agent only."""
    objective: str
    steps: list[str]
    relevant_files: list[str]
    constraints: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Usage:
    # input_tokens includes cached reads and cache writes; reasoning is an output subset.
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0

    def __post_init__(self):
        values = asdict(self)
        if any(type(v) is not int or v < 0 for v in values.values()):
            raise ValueError("Invalid provider usage")
        if self.cached_input_tokens + self.cache_write_tokens > self.input_tokens:
            raise ValueError("Cache usage exceeds input usage")
        if self.reasoning_tokens > self.output_tokens:
            raise ValueError("Reasoning tokens exceed output usage")

    @property
    def total(self):
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class AgentReply:
    calls: list[ToolCall]
    text: str = ""
    incomplete_reason: str = ""
