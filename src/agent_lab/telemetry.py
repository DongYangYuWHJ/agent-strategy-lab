import json
from pathlib import Path
from .domain import now, save_json


class Recorder:
    def __init__(self, directory: Path):
        self.directory = directory
        self.events = directory / "events.jsonl"
        self.sequence = 0

    def event(self, event_type, **fields):
        self.sequence += 1
        item = {"sequence": self.sequence, "timestamp": now(), "type": event_type, **fields}
        with self.events.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(item, ensure_ascii=False) + "\n")
            stream.flush()
        return item

    def snapshot(self, value):
        save_json(self.directory / "state.json", value)
