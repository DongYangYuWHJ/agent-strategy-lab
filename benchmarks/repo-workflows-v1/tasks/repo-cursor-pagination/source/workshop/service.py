from workshop.repository import Repository
from workshop.pagination import fetch
from workshop.tokens import decode
def run(request):
    limit = request.get("limit", 2)
    if type(limit) is not int or limit < 1:
        return {"error": "invalid_limit"}
    try:
        marker = decode(request["cursor"]) if request.get("cursor") is not None else None
    except ValueError:
        marker = None
    return fetch(Repository(request["records"]), limit, marker)
