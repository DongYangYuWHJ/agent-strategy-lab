from copy import deepcopy
class Repository:
    def __init__(self, documents):
        self.documents = {(d["tenant"], d["id"]): deepcopy(d) for d in documents}
        self.reads = 0
    def read(self, tenant, doc_id):
        self.reads += 1
        return deepcopy(self.documents[(tenant, doc_id)])
    def update(self, tenant, doc_id, title):
        self.documents[(tenant, doc_id)]["title"] = title
