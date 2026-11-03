def transaction(self):
    """Isolated, nested in-process transaction (not a durability guarantee)."""
    from contextlib import contextmanager
    from copy import deepcopy
    from .storages import MemoryStorage

    @contextmanager
    def scope():
        parent = self._storage
        original_tables = dict(self._tables)
        buffer = MemoryStorage()
        buffer.write(deepcopy(parent.read() or {}))
        self._storage = buffer
        for table in self._tables.values():
            table._storage = buffer
            table.clear_cache()
            table._next_id = None
        committed = False
        try:
            yield self
            parent.write(deepcopy(buffer.read() or {}))
            committed = True
        finally:
            handles = list(self._tables.values()) + list(original_tables.values())
            self._storage = parent
            if not committed:
                self._tables = original_tables
            for table in handles:
                table._storage = parent
                table.clear_cache()
                table._next_id = None
    return scope()
