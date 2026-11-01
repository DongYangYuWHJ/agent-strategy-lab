from workshop.cli import parse
from workshop.settings import load
from workshop.transport import build_request
def run(request):
    options = parse(request.get("argv", []))
    try:
        settings = load(request.get("config", {}), request.get("env", {}), {})
    except ValueError:
        return {"error": "invalid_timeout"}
    return build_request(options["target"], settings)
