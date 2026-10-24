"""Versioned model input counting; never generates model output."""
from copy import deepcopy
from functools import lru_cache
import hashlib
from importlib.metadata import version
import json
from pathlib import Path


class TokenCountError(ValueError):
    pass


ASSETS = Path(__file__).resolve().parents[2] / "assets" / "tokenizers" / "deepseek-v41"
DEEPSEEK_ASSETS = {
    "tokenizer.json": "81f64d1248a68ce3663e07ab3ee48b851e5df0e32d27cb98e4c9a268151e8d99",
    "chat_template.jinja": "d959d804d5101b79a49b6ff1bf3c54cd5affa9a5a78c503d925f3090040b31c3",
}


def validated_count(value):
    if type(value) is not int or value < 0:
        raise TokenCountError("Token counter returned an invalid input_tokens count")
    return value


class DeepSeekV41Counter:
    """Official V4.1 text tokenizer and chat template, loaded entirely locally."""
    def __init__(self):
        try:
            from jinja2.sandbox import ImmutableSandboxedEnvironment
            from tokenizers import Tokenizer
        except ImportError:
            raise TokenCountError('Install token counting dependencies: python -m pip install -e ".[token-counting]"') from None
        files = {}
        for name, expected in DEEPSEEK_ASSETS.items():
            try:
                data = (ASSETS / name).read_bytes()
            except OSError:
                raise TokenCountError(f"Missing DeepSeek tokenizer asset: {name}") from None
            if hashlib.sha256(data).hexdigest() != expected:
                raise TokenCountError(f"DeepSeek tokenizer asset checksum mismatch: {name}")
            files[name] = data
        self.tokenizer = Tokenizer.from_str(files["tokenizer.json"].decode("utf-8"))
        environment = ImmutableSandboxedEnvironment(trim_blocks=True, lstrip_blocks=True)
        # Match Hugging Face chat-template JSON rendering rather than Jinja's
        # default HTML-escaped, sorted JSON filter.
        environment.filters["tojson"] = lambda value, **kwargs: json.dumps(value, ensure_ascii=False, **kwargs)

        def fail(message):
            raise TokenCountError(message)
        environment.globals["raise_exception"] = fail
        self.template = environment.from_string(files["chat_template.jinja"].decode("utf-8"))
        self.metadata = {"mode": "model", "method": "deepseek_v41_local",
                         "template_revision": "314113f8a7dadb388215396ba5fbee2c610a04d6",
                         "tokenizer_revision": "935817c66f5d6e64838f419692545f06787e485f",
                         "asset_sha256": dict(DEEPSEEK_ASSETS),
                         "tokenizers_version": version("tokenizers"), "jinja2_version": version("Jinja2")}

    def count(self, payload):
        if payload.get("model") != "deepseek-flash":
            raise TokenCountError("The bundled V4.1 tokenizer is only configured for deepseek-flash")
        messages = deepcopy(payload["messages"])
        for message in messages:
            if message.get("content") is not None and not isinstance(message["content"], str):
                raise TokenCountError("The local DeepSeek counter currently supports text/tool messages only")
            # The official renderer consumes parsed tool arguments. Do this in
            # a copy: the original API request and reasoning history stay intact.
            for call in message.get("tool_calls") or []:
                function = call["function"]
                if isinstance(function.get("arguments"), str):
                    function["arguments"] = json.loads(function["arguments"])
                if not isinstance(function.get("arguments"), dict):
                    raise TokenCountError("Tool arguments must be a JSON object for token counting")
        thinking = payload.get("thinking", {}).get("type") != "disabled"
        rendered = self.template.render(messages=messages, tools=payload.get("tools"),
                                        thinking_mode="thinking" if thinking else "chat",
                                        reasoning_effort=payload.get("reasoning_effort", "low") if thinking else "low",
                                        drop_thinking=False, add_generation_prompt=True)
        return len(self.tokenizer.encode(rendered, add_special_tokens=False).ids)


@lru_cache(maxsize=1)
def deepseek_counter():
    return DeepSeekV41Counter()
