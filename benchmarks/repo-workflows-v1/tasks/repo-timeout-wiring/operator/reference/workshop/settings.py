from workshop.defaults import DEFAULT_TIMEOUT_MS
def load(config, env, cli):
    if cli.get("timeout_ms") is not None:
        value = cli["timeout_ms"]
    elif "APP_TIMEOUT_MS" in env:
        value = env["APP_TIMEOUT_MS"]
    else:
        value = config.get("timeout_ms", DEFAULT_TIMEOUT_MS)
    if type(value) is str:
        value = value.strip()
        if not value or any(c not in "0123456789" for c in value):
            raise ValueError("invalid timeout")
        value = int(value)
    if type(value) is not int or value < 0:
        raise ValueError("invalid timeout")
    return {"timeout_ms": value}
