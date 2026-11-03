"""Build nine Windows/stdlib-only development candidates; never call model APIs.

Pinned real repositories plus lab-authored feature contracts, not official issues.
Reference code and hidden cases remain outside agent source workspaces.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import textwrap
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "calibration_fixtures"
sys.path.insert(0, str(FIXTURES))
from tasks import TASKS

CHECK = '''from collections import defaultdict
from copy import deepcopy
import json
import os
from pathlib import Path
from check_client import load_submission

cases = json.loads(CASES_LITERAL)
submission = load_submission(Path(os.environ["LAB_WORKSPACE"]) / "app.py")
groups = defaultdict(lambda: {"passed": 0, "total": 0})
failures = []
outputs = submission.run_many([deepcopy(item["request"]) for item in cases])
assert isinstance(outputs, list) and len(outputs) == len(cases), "Incomplete batch result"
for index, item in enumerate(cases, 1):
    group = groups[item["group"]]
    group["total"] += 1
    try:
        response = outputs[index - 1]
        assert response.get("ok") is True, f"submission error: {response}"
        actual = response["value"]
        assert actual == item["expected"], f"expected {item['expected']!r}, got {actual!r}"
        group["passed"] += 1
    except Exception as exc:
        failures.append(f"case {index} [{item['group']}]: {str(exc)[:1000]}")
print("LAB_GROUP_RESULTS " + json.dumps(dict(groups), sort_keys=True), flush=True)
print(f"Passed {len(cases) - len(failures)}/{len(cases)} scenarios", flush=True)
assert not failures, "\\n".join(failures)
'''

BATCH_ADAPTER = '''


def run_many(requests):
    # Each run constructs independent library instances; the trusted host grades results.
    results = []
    for request in requests:
        try:
            results.append({"ok": True, "value": run(request)})
        except Exception as exc:
            results.append({"ok": False, "error": type(exc).__name__, "message": str(exc)[:500]})
    return results
'''


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def read_archive(source, download):
    archive = ROOT / source["archive"]
    if not archive.exists():
        if not download:
            raise ValueError("Missing source archive; use --download")
        url = f"https://codeload.github.com/{source['repo']}/zip/{source['commit']}"
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != source["sha256"]:
            raise ValueError("Downloaded source checksum mismatch")
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(data)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != source["sha256"]:
        raise ValueError("Cached source checksum mismatch")
    with zipfile.ZipFile(archive) as zipped:
        prefix = zipped.namelist()[0].split("/")[0] + "/"
        files = {}
        for member in zipped.namelist():
            name = member[len(prefix):]
            if (not name or member.endswith("/") or ".." in Path(name).parts
                    or any(part.startswith(".") for part in Path(name).parts)):
                continue
            if Path(name).suffix not in {".py", ".rst", ".md", ".txt", ".toml", ".cfg", ".ini", ".typed", ""}:
                continue
            files[name] = zipped.read(member).decode("utf-8")
    return files


def prepare(suite, download=False):
    if suite.exists():
        raise ValueError("Refusing to overwrite an existing suite")
    sources = json.loads((FIXTURES / "sources.json").read_text(encoding="utf-8"))
    contents = {(s["repo"], s["ref"]): read_archive(s, download) for s in sources}
    manifest = {"schema_version": 1, "id": "python-calibration-v1", "split": "development",
                "provenance": "Pinned real repositories; lab-authored feature contracts, tests and reference patches; not official upstream issues or benchmark scores.",
                "sources": sources, "tasks": []}
    for spec in TASKS:
        folder = suite / "tasks" / spec["id"]
        files = contents[spec["repo"], spec["ref"]]
        editable = sorted(name for name in files if name.startswith(spec["package"] + "/") and name.endswith(".py"))
        module, anchor = spec["module"], spec["anchor"]
        original = files[module]
        if original.count(anchor) != 1:
            raise ValueError("Class insertion anchor changed")
        implementations = spec["implementation"]
        if isinstance(implementations, str):
            implementations = [implementations]
        body = "\n\n".join((FIXTURES / name).read_text(encoding="utf-8") for name in implementations)
        reference = original.replace(anchor, anchor + textwrap.indent(body, "    ") + "\n\n", 1)
        for name, content in files.items():
            write(folder / "source" / name, content)
        for name in editable:
            write(folder / "operator/reference" / name, reference if name == module else files[name])
        for name, content in files.items():
            if "/" not in name and name.upper().startswith("LICENSE"):
                write(folder / "operator/reference-license" / name, content)
        write(folder / "source/app.py", (FIXTURES / spec["adapter"]).read_text(encoding="utf-8") + BATCH_ADAPTER)
        description = spec["title"] + "：在现有项目包内实现需求，保持只读 app.py 的协议。"
        write(folder / "source/LAB_TASK.md", "# " + spec["title"] + "\n\n" + description + "\n\n" +
              "\n\n".join(f"{i}. {text}" for i, text in enumerate(spec["acceptance"], 1)) +
              "\n\n这是人工整理的新功能合同，不是上游原始 issue。只需 Python 标准库和附带源码；不需要 pip 安装、网络或额外服务。原上游 pytest 测试供阅读，受支持的执行验收为 tests_lab 公开场景。允许使用工具反复测试和修复。\n")
        public, final = spec["cases"]()
        task = {"schema_version": 1, "id": spec["id"], "description": description,
                "acceptance": spec["acceptance"], "source_dir": "source", "editable_files": editable,
                "public_check": "public_check.py", "final_check": "final_check.py"}
        write(folder / "task.json", json.dumps(task, ensure_ascii=False, indent=2) + "\n")
        for kind, cases in (("public", public), ("final", final)):
            write(folder / (kind + "_check.py"), CHECK.replace("CASES_LITERAL", repr(json.dumps(cases))))
        write(folder / "source/tests_lab/test_public.py",
              "import json\nimport unittest\nfrom app import run\nCASES = json.loads(" + repr(json.dumps(public)) + ")\n\n"
              "class PublicScenarios(unittest.TestCase):\n    def test_contract(self):\n        for item in CASES:\n"
              "            with self.subTest(group=item['group']):\n                self.assertEqual(run(item['request']), item['expected'])\n")
        for name, old, new in spec["mutants"]:
            if not body.count(old):
                raise ValueError("Mutation anchor changed")
            mutant = original.replace(anchor, anchor + textwrap.indent(body.replace(old, new), "    ") + "\n\n", 1)
            write(folder / "operator/mutants" / (name + ".json"), json.dumps({module: mutant}, indent=2) + "\n")
        row = {"id": spec["id"], "manifest": "tasks/" + spec["id"] + "/task.json", "repo": spec["repo"],
               "baseline": spec["ref"], "difficulty": "unmeasured", "editable_files": len(editable),
               "family": spec["repo"], "scope": spec.get("scope", "focused"),
               "package_python_lines": sum(len(files[name].splitlines()) for name in editable),
               "public_scenarios": len(public), "final_scenarios": len(final),
               "groups": dict(Counter(case["group"] for case in final))}
        manifest["tasks"].append(row)
        print(json.dumps(row, ensure_ascii=True), flush=True)
    write(suite / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    write(suite / "README.md", "# Python calibration candidates v1\n\nNine development tasks across three pinned real libraries.\n"
          "Custom feature contracts, not upstream issues. Difficulty and model discrimination remain unmeasured.\n"
          "Three integrated tasks reuse the six focused contracts; these are not nine independent samples.\n"
          "Only source/ is provided to agents. operator/ and final_check.py must remain outside their workspaces.\n"
          "See docs/task-calibration.md for scope, audit evidence and preparation.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks/python-calibration-v1")
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    prepare(args.output.resolve(), args.download)
