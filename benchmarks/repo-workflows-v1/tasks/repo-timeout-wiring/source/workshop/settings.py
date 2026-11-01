from workshop.defaults import DEFAULT_TIMEOUT_MS
def load(config, env, cli):
    return {"timeout_ms": config.get("timeout_ms") or DEFAULT_TIMEOUT_MS}
