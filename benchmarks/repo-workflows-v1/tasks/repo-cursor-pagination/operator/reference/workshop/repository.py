class Repository:
    def __init__(self, records):
        self.records = records
    def ordered(self):
        return sorted(self.records, key=lambda r: (r["created_at"], r["id"]))
