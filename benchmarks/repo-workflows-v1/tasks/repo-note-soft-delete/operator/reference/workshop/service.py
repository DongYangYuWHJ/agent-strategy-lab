from workshop.repository import Repository
from workshop.views import present
def run(request):
    repo = Repository(request.get("notes", []))
    results = []
    for operation in request.get("operations", []):
        action = operation["op"]
        if action == "list":
            results.append([present(n) for n in repo.list(operation.get("include_deleted", False))])
        elif action == "get":
            note = repo.get(operation["id"], operation.get("include_deleted", False))
            results.append(present(note) if note is not None else {"error": "not_found"})
        elif action in ("delete", "restore"):
            ok = getattr(repo, action)(operation["id"])
            results.append({"ok": True} if ok else {"error": "not_found"})
        elif action == "create":
            note = repo.create(operation["id"], operation["text"])
            results.append(present(note) if note is not None else {"error": "conflict"})
        elif action == "update":
            note = repo.update(operation["id"], operation["text"])
            results.append(present(note) if note is not None else {"error": "not_found"})
        else:
            raise ValueError("unsupported operation")
    return {"results": results}
