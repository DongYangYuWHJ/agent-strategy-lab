"""Usage-based estimated cost, reservations, and hard execution counters."""
from dataclasses import asdict
from decimal import Decimal
from .domain import Limits, Model, Pricing, Usage, money


class StopRun(Exception):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def usage_cost(usage: Usage, rates: Pricing) -> Decimal:
    rates = rates.for_input(usage.input_tokens)
    fresh = usage.input_tokens - usage.cached_input_tokens - usage.cache_write_tokens
    return (fresh * money(rates.input) + usage.cached_input_tokens * money(rates.cached_input)
            + usage.cache_write_tokens * money(rates.cache_write)
            + usage.output_tokens * money(rates.output)) / Decimal(1000000)


class Ledger:
    def __init__(self, limits: Limits):
        self.limits = limits
        self.calls = 0
        self.tool_steps = 0
        self.tokens = 0
        self.token_budget_tokens = 0
        self.cost = Decimal(0)
        self.unknown_cost_reserve = Decimal(0)
        self.unknown_calls = 0
        self.usage = {k: 0 for k in asdict(Usage(0, 0))}
        self.records = []

    def reserve(self, model: Model, request_bytes: int, estimated_input_tokens: int | None = None):
        if self.limits.max_calls is not None and self.calls >= self.limits.max_calls:
            raise StopRun("call_limit")
        if self.limits.max_request_bytes is not None and request_bytes > self.limits.max_request_bytes:
            raise StopRun("request_size_limit")
        # Provider-specific estimate, independent of wire size. The fallback is
        # deliberately conservative, not a certified tokenizer/billing guarantee.
        input_reserve = request_bytes + 2048 if estimated_input_tokens is None else estimated_input_tokens
        if type(input_reserve) is not int or input_reserve < 1:
            raise ValueError("Invalid estimated input tokens")
        if self.limits.max_estimated_input_tokens is not None and input_reserve > self.limits.max_estimated_input_tokens:
            raise StopRun("input_estimate_limit")
        token_reserve = input_reserve + model.output_reserve_tokens
        rates = model.pricing.for_input(input_reserve)
        max_input_rate = max(money(rates.input), money(rates.cache_write), money(rates.cached_input))
        reserve = (input_reserve * max_input_rate + model.output_reserve_tokens * money(rates.output)) / Decimal(1000000)
        if model.enforce_total_token_limit and self.limits.max_total_tokens is not None and self.token_budget_tokens + token_reserve > self.limits.max_total_tokens:
            raise StopRun("token_limit")
        if self.limits.max_cost_usd is not None and self.cost + self.unknown_cost_reserve + reserve > money(self.limits.max_cost_usd):
            raise StopRun("budget_limit")
        self.calls += 1
        return reserve

    def record(self, model: Model, usage: Usage, response_id: str, returned_model: str):
        cost = usage_cost(usage, model.pricing)
        self.cost += cost
        self.tokens += usage.total
        if model.enforce_total_token_limit:
            self.token_budget_tokens += usage.total
        for key, value in asdict(usage).items():
            self.usage[key] += value
        entry = {"call": self.calls, "model_config_id": model.id, "returned_model": returned_model,
                 "response_id": response_id, "usage": asdict(usage), "estimated_cost_usd": str(cost)}
        if model.pricing.long_context_threshold is not None:
            entry["pricing_tier"] = "long" if usage.input_tokens > model.pricing.long_context_threshold else "short"
        self.records.append(entry)
        return entry

    def check_observed_limits(self):
        if self.limits.max_cost_usd is not None and self.cost > money(self.limits.max_cost_usd):
            raise StopRun("budget_limit")
        if self.limits.max_total_tokens is not None and self.token_budget_tokens > self.limits.max_total_tokens:
            raise StopRun("token_limit")

    def tool_step(self):
        if self.limits.max_tool_steps is not None and self.tool_steps >= self.limits.max_tool_steps:
            raise StopRun("tool_limit")
        self.tool_steps += 1

    def mark_unknown(self, reservation):
        self.unknown_calls += 1
        self.unknown_cost_reserve += reservation

    def summary(self):
        return {"calls": self.calls, "tool_steps": self.tool_steps,
                "total_tokens": self.tokens, "token_budget_tokens": self.token_budget_tokens, "usage": self.usage,
                "estimated_cost_usd": str(self.cost),
                "unknown_cost_reserve_usd": str(self.unknown_cost_reserve),
                "unknown_calls": self.unknown_calls,
                "usage_complete": self.unknown_calls == 0}
