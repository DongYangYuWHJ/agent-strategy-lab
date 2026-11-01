from copy import deepcopy
from workshop.repository import Repository
from workshop.cache import Cache
from workshop.documents import Service
def run(request):
    repo = Repository(request["documents"])
    service, results, last = Service(repo, Cache()), [], None
    for action in request["actions"]:
        if action["op"] == "read":
            last = service.read(action["tenant"], action["id"], action["role"])
            results.append(deepcopy(last))
        elif action["op"] == "mutate_last":
            last[action["field"]] = action["value"]
            results.append({"ok": True})
        elif action["op"] == "update":
            service.update(action["tenant"], action["id"], action["title"])
            results.append({"ok": True})
    return {"results": results, "repository_reads": repo.reads}
