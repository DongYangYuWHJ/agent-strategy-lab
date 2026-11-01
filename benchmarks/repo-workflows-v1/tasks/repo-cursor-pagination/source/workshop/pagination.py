from workshop.tokens import encode
def fetch(repository, limit, marker):
    rows = repository.ordered()
    if marker is not None:
        rows = [r for r in rows if r["created_at"] > marker[0]]
    page = rows[:limit]
    next_cursor = encode((page[-1]["created_at"], page[-1]["id"])) if page else None
    return {"items": page, "next_cursor": next_cursor}
