from copy import deepcopy
class Cache:
    def __init__(self):
        self.entries = {}
    def get(self, key):
        return deepcopy(self.entries.get(key))
    def put(self, key, value):
        self.entries[key] = deepcopy(value)
    def invalidate_document(self, tenant, doc_id):
        for key in list(self.entries):
            if key[:2] == (tenant, doc_id):
                del self.entries[key]
