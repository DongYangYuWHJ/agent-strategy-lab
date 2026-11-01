from workshop.tokens import encode
def fetch(repository, limit, marker):
    rows = repository.ordered()
    if marker is not None:
        rows = [r for r in rows if (r["created_at"], r["id"]) > marker]
    page = rows[:limit]
    next_cursor = encode((page[-1]["created_at"], page[-1]["id"])) if len(rows) > len(page) else None
    return {"items": page, "next_cursor": next_cursor}
