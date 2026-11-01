from workshop.paging import paginate
def run(request):
    try:
        return paginate(request["items"], request.get("page", 1), request.get("page_size", 20))
    except ValueError:
        return {"error": "invalid_pagination"}
