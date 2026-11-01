from workshop.transport import Transport
from workshop.clock import Clock
from workshop.retry import execute
def run(request):
    transport, clock = Transport(request["responses"]), Clock()
    try:
        result = execute(transport, clock, request.get("max_attempts", 3), request.get("base_delay", 1))
    except ValueError:
        return {"error": "invalid_retry_options"}
    return {"status": result["status"], "body": result.get("body"), "attempts": transport.attempts, "delays": clock.delays}
