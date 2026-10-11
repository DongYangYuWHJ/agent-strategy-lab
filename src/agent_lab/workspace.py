"""Copy isolation and constrained file tools. This is NOT an OS sandbox."""
import difflib
import hashlib
from pathlib import Path
import shutil
from .domain import relative_path


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(root: Path):
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Symlinks are not supported in experiment sources")
        if not path.is_file() or any(part.startswith(".") or part == "__pycache__" for part in path.relative_to(root).parts):
            continue
        if path.suffix in {".pyc", ".pyo"}:
            continue
        if path.stat().st_size > 1000000:
            raise ValueError("v1 source files must be <= 1 MB")
        result[path.relative_to(root).as_posix()] = file_hash(path)
    if not result:
        raise ValueError("No source files found")
    return result


class Workspace:
    def __init__(self, task, run_dir):
        self.root = run_dir / "workspace"
        self.baseline = run_dir / "baseline"
        self.editable = set(task.editable_files)
        self.original = inventory(task.source_dir)
        if self.root.resolve().is_relative_to(task.source_dir) or task.source_dir.is_relative_to(run_dir.resolve()):
            raise ValueError("Run directory and task source must not overlap")
        self.root.mkdir()
        self.baseline.mkdir()
        for name in self.original:
            for dest in (self.root, self.baseline):
                target = dest / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(task.source_dir / name, target)
        self.allowed = set(self.original) | self.editable

    def resolve(self, value, writable=False):
        name = relative_path(value)
        if name not in (self.editable if writable else self.allowed):
            raise ValueError("Path is outside the task file allowlist")
        candidate = self.root / name
        for path in (candidate, *candidate.parents):
            if path == self.root.parent:
                break
            if path.is_symlink():
                raise ValueError("Symlinks are not available to agents")
        if not candidate.resolve().is_relative_to(self.root.resolve()):
            raise ValueError("Path escapes workspace")
        return candidate

    def list_files(self):
        return sorted(name for name in self.allowed if (self.root / name).is_file())

    def read_file(self, path):
        content = self.resolve(path).read_text(encoding="utf-8")
        return {"path": path, "content": content[:12000], "truncated": len(content) > 12000}

    def write_file(self, path, content):
        if not isinstance(content, str) or len(content.encode("utf-8")) > 64000:
            raise ValueError("Writes must be UTF-8 text <= 64000 bytes")
        target = self.resolve(path, writable=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {"path": path, "bytes": target.stat().st_size}

    def search(self, query):
        if not isinstance(query, str) or not 1 <= len(query) <= 1000:
            raise ValueError("Search query must be 1-1000 characters")
        matches = []
        for name in self.list_files():
            try:
                for number, line in enumerate(self.resolve(name).read_text(encoding="utf-8").splitlines(), 1):
                    if query in line:
                        matches.append({"path": name, "line": number, "text": line[:400]})
                        if len(matches) >= 40:
                            return {"matches": matches, "truncated": True}
            except UnicodeError:
                continue
        return {"matches": matches, "truncated": False}

    def fingerprint(self):
        from .domain import digest
        return digest(inventory(self.root))

    def verify_immutable(self):
        current = inventory(self.root)
        changed = {name for name in set(current) | set(self.original) if current.get(name) != self.original.get(name)}
        if changed - self.editable:
            raise ValueError("Files outside editable_files changed")

    def export_diff(self, destination):
        chunks = []
        current = inventory(self.root)
        for name in sorted(set(current) | set(self.original)):
            before = self.baseline / name
            after = self.root / name
            left = before.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True) if before.exists() else []
            right = after.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True) if after.exists() else []
            chunks.extend(difflib.unified_diff(left, right, fromfile="a/" + name, tofile="b/" + name))
        destination.write_text("".join(chunks), encoding="utf-8")
