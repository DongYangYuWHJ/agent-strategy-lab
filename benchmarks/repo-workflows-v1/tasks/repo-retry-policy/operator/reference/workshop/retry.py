from math import isfinite
def execute(transport, clock, max_attempts, base_delay):
    if type(max_attempts) is not int or max_attempts < 1:
        raise ValueError("invalid attempts")
    if type(base_delay) not in (int, float) or not isfinite(base_delay) or base_delay < 0:
        raise ValueError("invalid delay")
    retryable = {429, 500, 502, 503, 504}
    for attempt in range(1, max_attempts + 1):
        result = transport.send()
        if result["status"] not in retryable or attempt == max_attempts:
            return result
        hint = result.get("retry_after")
        delay = hint if type(hint) in (int, float) and hint >= 0 else base_delay * 2 ** (attempt - 1)
        clock.sleep(delay)
