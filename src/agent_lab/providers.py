"""Native tool protocols behind one execution interface. No SDK dependency."""
from dataclasses import asdict
import json
import socket
import urllib.error
import urllib.request
from .domain import AgentReply, Model, ToolCall, Usage, read_json
from .settings import require_credential
from .token_counting import TokenCountError, deepseek_counter, validated_count


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

    def estimate_input_tokens(self, payload):
        # One token per serialized UTF-8 byte plus protocol margin: conservative
        # for plain text, but not appropriate for opaque encrypted state.
        return len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) + 2048

    def token_counting_info(self):
        return {"mode": self.model.token_counting,
                "method": "legacy_estimate" if self.model.token_counting == "estimate" else self.model.provider + "_count_api"}

    def count_input_tokens(self, payload, timeout):
        raise TokenCountError("No model token counter is configured for this provider")

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
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._encrypted_output_token_allowance = 0

    def preflight(self):
        self._api_key = require_credential("openai")

    def prepare(self):
        payload = {"model": self.model.model, "instructions": self.system, "input": self.messages,
                "tools": [{"type": "function", "strict": True, **tool} for tool in self.tools],
                "max_output_tokens": self.model.max_output_tokens,
                "reasoning": {"effort": self.model.reasoning_effort}, "store": False,
                "include": ["reasoning.encrypted_content"]}
        if self.model.max_output_tokens is None:
            payload.pop("max_output_tokens")
        return payload

    def send(self, payload, timeout):
        return request_json("https://api.openai.com/v1/responses", payload,
                            {"Authorization": "Bearer " + self._api_key}, timeout)

    def count_input_tokens(self, payload, timeout):
        count_payload = {key: payload[key] for key in ("model", "instructions", "input", "tools")}
        try:
            raw = request_json("https://api.openai.com/v1/responses/input_tokens", count_payload,
                               {"Authorization": "Bearer " + self._api_key}, timeout)
            return validated_count(raw["input_tokens"])
        except ProviderError as exc:
            raise TokenCountError(f"OpenAI token count endpoint failed: {exc}; no generation request was sent") from None
        except (KeyError, TypeError, ValueError):
            raise TokenCountError("OpenAI input token counting failed; no generation request was sent") from None

    def usage(self, raw):
        usage = raw["usage"]
        details = usage.get("input_tokens_details") or {}
        return Usage(usage["input_tokens"], usage["output_tokens"],
                     details.get("cached_tokens", 0), details.get("cache_write_tokens", 0),
                     (usage.get("output_tokens_details") or {}).get("reasoning_tokens", 0))

    def estimate_input_tokens(self, payload):
        # Keep every encrypted block unchanged ON THE WIRE. For admission only,
        # replace its bytes with the full output-token count of its source
        # response. Counting all output (not just reasoning) errs on the high
        # side, and still counts the visible fields below. No decryption occurs.
        visible_payload = {**payload, "input": [
            {key: value for key, value in item.items() if key != "encrypted_content"}
            if item.get("type") == "reasoning" else item for item in payload["input"]]}
        return super().estimate_input_tokens(visible_payload) + self._encrypted_output_token_allowance

    def accept(self, raw):
        if raw.get("status") == "incomplete":
            return AgentReply([], incomplete_reason=(raw.get("incomplete_details") or {}).get("reason") or "unknown")
        if raw.get("status") in {"failed", "cancelled", "queued", "in_progress"}:
            return AgentReply([], incomplete_reason="response_" + raw["status"])
        items = raw.get("output", [])
        if any(item.get("status") == "incomplete" for item in items):
            return AgentReply([], incomplete_reason="incomplete_output_item")
        if any(item.get("type") == "reasoning" and item.get("encrypted_content") for item in items):
            # Normal execution validates usage before accepting a response. The
            # fallback also makes direct protocol/fixture use conservative.
            output_tokens = (raw.get("usage") or {}).get("output_tokens", self.model.output_reserve_tokens)
            if type(output_tokens) is not int or output_tokens < 0:
                raise ValueError("Invalid encrypted continuation token allowance")
            self._encrypted_output_token_allowance += output_tokens
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
        if self.model.token_counting == "model":
            deepseek_counter()

    def token_counting_info(self):
        if self.model.token_counting == "model":
            return deepseek_counter().metadata
        return super().token_counting_info()

    def count_input_tokens(self, payload, timeout):
        try:
            return validated_count(deepseek_counter().count(payload))
        except TokenCountError:
            raise
        except Exception as exc:
            raise TokenCountError(f"DeepSeek local input token counting failed ({type(exc).__name__}); no generation request was sent") from None

    def prepare(self):
        payload = {"model": self.model.model,
                "messages": [{"role": "system", "content": self.system}, *self.messages],
                "tools": [{"type": "function", "function": tool} for tool in self.tools],
                "max_tokens": self.model.max_output_tokens,
                "thinking": {"type": "disabled" if self.model.reasoning_effort == "none" else "enabled"},
                "reasoning_effort": self.model.reasoning_effort}
        if self.model.max_output_tokens is None:
            payload.pop("max_tokens")
        return payload

    def send(self, payload, timeout):
        return request_json("https://api.deepseek.com/chat/completions", payload,
                            {"Authorization": "Bearer " + self._api_key}, timeout)

    def usage(self, raw):
        usage = raw["usage"]
        cached = usage.get("prompt_cache_hit_tokens", (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0))
        return Usage(usage["prompt_tokens"], usage["completion_tokens"], cached, 0,
                     (usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0))

    def accept(self, raw):
        if raw["choices"][0].get("finish_reason") == "length":
            # DeepSeek uses length for both output and context length limits.
            # The runner compares measured output with the configured cap.
            return AgentReply([], incomplete_reason="length")
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

    def count_input_tokens(self, payload, timeout):
        count_payload = {key: payload[key] for key in ("model", "system", "messages", "tools", "thinking")}
        try:
            raw = request_json("https://api.anthropic.com/v1/messages/count_tokens", count_payload,
                               {"x-api-key": self._api_key, "anthropic-version": "2023-06-01"}, timeout)
            return validated_count(raw["input_tokens"])
        except ProviderError as exc:
            raise TokenCountError(f"Claude token count endpoint failed: {exc}; no generation request was sent") from None
        except (KeyError, TypeError, ValueError):
            raise TokenCountError("Claude input token counting failed; no generation request was sent") from None

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
        if raw.get("stop_reason") == "max_tokens":
            return AgentReply([], incomplete_reason="max_output_tokens")
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
