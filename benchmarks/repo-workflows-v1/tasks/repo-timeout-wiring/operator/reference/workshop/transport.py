def build_request(target, settings):
    timeout = settings["timeout_ms"]
    return {"target": target, "timeout_ms": timeout,
            "timeout_seconds": None if timeout == 0 else timeout / 1000,
            "headers": {"User-Agent": "lab-client/1"}}
