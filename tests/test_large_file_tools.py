"""Long-source access, unique edits and the read-only phase boundary."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from agent_lab.domain import Task
from agent_lab.workspace import Workspace
from agent_lab.workflow_gateway import role_tool_definitions


class LargeFileToolsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        # Reuse a valid task contract, while giving it an isolated long source.
        from dataclasses import replace
        source = root / "source"
        source.mkdir()
        self.original = "header\n" + "x" * 70000 + "\nunique tail\n"
        (source / "long.py").write_text(self.original, encoding="utf-8")
        (source / "readonly.txt").write_text("protected", encoding="utf-8")
        task = replace(Task.load(ROOT / "tickets/clamp-boundaries/task.json"),
                       source_dir=source, editable_files=("long.py",))
        run = root / "run"
        run.mkdir()
        self.workspace = Workspace(task, run)

    def test_paging_reconstructs_entire_long_file(self):
        pieces, offset = [], "0"
        while True:
            result = self.workspace.read_file_chunk("long.py", offset)
            self.assertLessEqual(len(result["content"]), 12000)
            pieces.append(result["content"])
            if result["next_offset"] is None:
                break
            offset = str(result["next_offset"])
        self.assertEqual("".join(pieces), self.original)

    def test_unique_edit_preserves_rest_of_file_and_allowlist(self):
        self.workspace.edit_file("long.py", "unique tail", "replacement")
        self.assertEqual((self.workspace.root / "long.py").read_text(encoding="utf-8"),
                         self.original.replace("unique tail", "replacement"))
        for path, old in [("readonly.txt", "protected"), ("../outside.py", "x")]:
            with self.assertRaises(ValueError):
                self.workspace.edit_file(path, old, "bad")

    def test_ambiguous_or_absent_edits_leave_file_unchanged(self):
        for old in ["x", "absent", ""]:
            with self.assertRaises(ValueError):
                self.workspace.edit_file("long.py", old, "wrong")
        self.assertEqual((self.workspace.root / "long.py").read_text(encoding="utf-8"), self.original)

    def test_invalid_offsets_and_path_escape(self):
        for offset in ["-1", "1.5", "999999999", "", "01x"]:
            with self.assertRaises(ValueError):
                self.workspace.read_file_chunk("long.py", offset)
        with self.assertRaises(ValueError):
            self.workspace.read_file_chunk("../outside", "0")

    def test_planner_has_no_edit_tool(self):
        names = {t["name"] for t in role_tool_definitions("planner")}
        self.assertIn("read_file_chunk", names)
        self.assertFalse(names & {"write_file", "edit_file"})
        self.assertIn("edit_file", {t["name"] for t in role_tool_definitions("solo")})


if __name__ == "__main__":
    unittest.main()
