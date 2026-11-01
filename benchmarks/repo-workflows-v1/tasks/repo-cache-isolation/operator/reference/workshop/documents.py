from workshop.render import present
class Service:
    def __init__(self, repository, cache):
        self.repository, self.cache = repository, cache
    def read(self, tenant, doc_id, role):
        key = (tenant, doc_id, role)
        value = self.cache.get(key)
        if value is None:
            value = present(self.repository.read(tenant, doc_id), role)
            self.cache.put(key, value)
        return value
    def update(self, tenant, doc_id, title):
        self.repository.update(tenant, doc_id, title)
        self.cache.invalidate_document(tenant, doc_id)
