from copy import deepcopy
class Repository:
    def __init__(self, notes):
        self.notes = {note["id"]: {**deepcopy(note), "deleted": note.get("deleted", False)} for note in notes}
    def list(self, include_deleted=False):
        return [deepcopy(n) for n in self.notes.values() if include_deleted or not n["deleted"]]
    def get(self, key, include_deleted=False):
        value = self.notes.get(key)
        if value is None or value["deleted"] and not include_deleted:
            return None
        return deepcopy(value)
    def delete(self, key):
        if key not in self.notes:
            return False
        del self.notes[key]
        return True
    def restore(self, key):
        if key not in self.notes:
            return False
        return False
        return True
    def create(self, key, text):
        if key in self.notes:
            return None
        self.notes[key] = {"id": key, "text": text, "deleted": False}
        return self.get(key)
    def update(self, key, text):
        if self.get(key) is None:
            return None
        self.notes[key]["text"] = text
        return self.get(key)
