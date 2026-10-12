"""Native tool protocols behind one execution interface. No SDK dependency."""
from dataclasses import asdict
import json
import socket
import urllib.error
import urllib.request
from .domain import AgentReply, Model, ToolCall, Usage, read_json
from .settings import require_credential


class ProviderError(Exception):
    """The request may have been billed; never silently retry it."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProviderError("Unexpected API redirect")


def request_json(url, payload, headers, timeout):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **headers}, method="POST")
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            body = response.read(16 * 1024 * 1024 + 1)
        if len(body) > 16 * 1024 * 1024:
            raise ProviderError("API response exceeds size limit; usage is unknown")
        return json.loads(body)
    except urllib.error.HTTPError as exc:
        # Do not log response bodies or authorization headers.
        raise ProviderError(f"API returned HTTP {exc.code}; usage is unknown") from None
    except (urllib.error.URLError, TimeoutError, socket.timeout, json.JSONDecodeError) as exc:
        raise ProviderError(f"API transport/decoding error ({type(exc).__name__}); usage is unknown") from None


def arguments(value):
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
        return parsed if isinstance(parsed, dict) else {"_invalid_arguments": True}
    except (TypeError, json.JSONDecodeError):
        return {"_invalid_arguments": True}


class Provider:
    def __init__(self, model: Model, system: str, task_text: str, tools: list):
        self.model = model
        self.system = system
        self.messages = [{"role": "user", "content": task_text}]
        self.tools = tools

    def add_user(self, text):
        self.messages.append({"role": "user", "content": text})

    def prepare(self):
        raise NotImplementedError

    def send(self, payload, timeout):
        raise NotImplementedError

    def usage(self, raw):
        raise NotImplementedError

    def accept(self, raw):
        raise NotImplementedError

    def add_results(self, results):
        raise NotImplementedError

    def preflight(self):
        pass


class OpenAIProvider(Provider):
    def preflight(self):
        self._api_key = require_credential("openai")

    def prepare(self):
        return {"model": self.model.model, "instructions": self.system, "input": self.messages,
                "tools": [{"type": "function", "strict": True, **tool} for tool in self.tools],
                "max_output_tokens": self.model.max_output_tokens,
                "reasoning": {"effort": self.model.reasoning_effort}, "store": False,
                "include": ["reasoning.encrypted_content"]}

    def send(self, payload, timeout):
        return request_json("https://api.openai.com/v1/responses", payload,
                            {"Authorization": "Bearer " + self._api_key}, timeout)

    def usage(self, raw):
        usage = raw["usage"]
        details = usage.get("input_tokens_details") or {}
        return Usage(usage["input_tokens"], usage["output_tokens"],
                     details.get("cached_tokens", 0), details.get("cache_write_tokens", 0),
                     (usage.get("output_tokens_details") or {}).get("reasoning_tokens", 0))

    def accept(self, raw):
        items = raw.get("output", [])
        # Retain reasoning and encrypted continuation blocks, not just text.
        self.messages.extend(items)
        calls = [ToolCall(item["call_id"], item["name"], arguments(item["arguments"]))
                 for item in items if item.get("type") == "function_call"]
        text = "\n".join(block.get("text", "") for item in items if item.get("type") == "message"
                         for block in item.get("content", []) if block.get("type") == "output_text")
        return AgentReply(calls, text)

    def add_results(self, results):
        self.messages.extend({"type": "function_call_output", "call_id": call.id,
                              "output": json.dumps(result, ensure_ascii=False)} for call, result in results)


class DeepSeekProvider(Provider):
    def preflight(self):
        self._api_key = require_credential("deepseek")

    def prepare(self):
        return {"model": self.model.model,
                "messages": [{"role": "system", "content": self.system}, *self.messages],
                "tools": [{"type": "function", "function": tool} for tool in self.tools],
                "max_tokens": self.model.max_output_tokens,
                "thinking": {"type": "disabled" if self.model.reasoning_effort == "none" else "enabled"},
                "reasoning_effort": self.model.reasoning_effort}

    def send(self, payload, timeout):
        return request_json("https://api.deepseek.com/chat/completions", payload,
                            {"Authorization": "Bearer " + self._api_key}, timeout)

    def usage(self, raw):
        usage = raw["usage"]
        cached = usage.get("prompt_cache_hit_tokens", (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0))
        return Usage(usage["prompt_tokens"], usage["completion_tokens"], cached, 0,
                     (usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0))

    def accept(self, raw):
        message = raw["choices"][0]["message"]
        # Thinking-mode tool cycles require the original reasoning_content.
        self.messages.append(message)
        calls = [ToolCall(item["id"], item["function"]["name"], arguments(item["function"]["arguments"]))
                 for item in message.get("tool_calls", [])]
        return AgentReply(calls, message.get("content") or "")

    def add_results(self, results):
        self.messages.extend({"role": "tool", "tool_call_id": call.id,
                              "content": json.dumps(result, ensure_ascii=False)} for call, result in results)


class AnthropicProvider(Provider):
    def preflight(self):
        self._api_key = require_credential("anthropic")

    def prepare(self):
        return {"model": self.model.model, "system": self.system, "messages": self.messages,
                "tools": [{"name": tool["name"], "description": tool["description"],
                           "input_schema": tool["parameters"]} for tool in self.tools],
                "max_tokens": self.model.max_output_tokens, "thinking": {"type": "adaptive"},
                "output_config": {"effort": self.model.reasoning_effort}}

    def send(self, payload, timeout):
        return request_json("https://api.anthropic.com/v1/messages", payload,
                            {"x-api-key": self._api_key, "anthropic-version": "2023-06-01"}, timeout)

    def usage(self, raw):
        usage = raw["usage"]
        read = usage.get("cache_read_input_tokens", 0)
        write = usage.get("cache_creation_input_tokens", 0)
        # Anthropic input_tokens EXCLUDES cache-read and cache-creation tokens.
        # v1 never requests caching, so a 1h write would require new pricing support.
        if (usage.get("cache_creation") or {}).get("ephemeral_1h_input_tokens", 0):
            raise ValueError("1h cache pricing is not supported")
        return Usage(usage["input_tokens"] + read + write, usage["output_tokens"], read, write,
                     (usage.get("output_tokens_details") or {}).get("thinking_tokens", 0))

    def accept(self, raw):
        blocks = raw["content"]
        self.messages.append({"role": "assistant", "content": blocks})
        calls = [ToolCall(item["id"], item["name"], arguments(item["input"]))
                 for item in blocks if item.get("type") == "tool_use"]
        return AgentReply(calls, "\n".join(item["text"] for item in blocks if item.get("type") == "text"))

    def add_results(self, results):
        if results:
            self.messages.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": call.id,
                 "content": json.dumps(result, ensure_ascii=False), "is_error": not result.get("ok", False)}
                for call, result in results]})


class MockProvider(Provider):
    """Deterministic fixture replay; this is plumbing verification, not AI."""
    def __init__(self, *args, replay_path, **kwargs):
        super().__init__(*args, **kwargs)
        self.replay = read_json(replay_path)
        self.index = 0

    def prepare(self):
        return {"system": self.system, "messages": self.messages, "tools": self.tools,
                "max_output_tokens": self.model.max_output_tokens}

    def send(self, payload, timeout):
        self.index += 1
        behavior = self.model.mock_behavior
        if behavior == "stuck":
            actions = [{"name": "submit", "arguments": {"summary": "Done"}}]
        elif behavior == "invalid":
            actions = [{"name": "read_file", "arguments": {"path": "../private.py"}}]
        else:
            actions = self.replay[min(self.index - 1, len(self.replay) - 1)]
        raw = {"id": f"mock-{self.index}", "model": self.model.model,
               "reply": {"calls": [{"id": f"call-{self.index}-{i}", **action} for i, action in enumerate(actions)]},
               "usage": {"input_tokens": len(json.dumps(payload)) // 4 + 1,
                         "output_tokens": len(json.dumps(actions)) // 4 + 1}}
        if behavior == "missing_usage":
            raw.pop("usage")
        return raw

    def usage(self, raw):
        return Usage(**raw["usage"])

    def accept(self, raw):
        self.messages.append({"role": "assistant", "content": raw["reply"]})
        return AgentReply([ToolCall(item["id"], item["name"], item["arguments"]) for item in raw["reply"]["calls"]])

    def add_results(self, results):
        self.messages.extend({"role": "tool", "id": call.id, "content": result} for call, result in results)


def make_provider(model, system, task_text, tools, task):
    classes = {"openai": OpenAIProvider, "deepseek": DeepSeekProvider, "anthropic": AnthropicProvider}
    if model.provider == "mock":
        provider = MockProvider(model, system, task_text, tools, replay_path=task.manifest_path.parent / "replay.json")
    else:
        provider = classes[model.provider](model, system, task_text, tools)
    provider.preflight()
    return provider
