def paginate(items, page=1, page_size=20):
    if type(page) is not int or type(page_size) is not int or page < 1 or page_size < 1:
        raise ValueError("invalid pagination")
    total = len(items)
    start = (page - 1) * page_size
    total_pages = (total + page_size - 1) // page_size
    return {"items": items[start:start + page_size], "page": page, "page_size": page_size,
            "total": total, "total_pages": total_pages, "has_next": page < total_pages}
