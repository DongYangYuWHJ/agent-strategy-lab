def present(document, role):
    result = {"id": document["id"], "title": document["title"]}
    if role == "admin":
        result["secret"] = document["secret"]
    return result
