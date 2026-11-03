"""Prepare two pinned, real pure-Python repository upgrade tasks (no pip needed).

Historical release source is used as a positive control. These are curated
upgrade contracts, NOT original upstream issues or the complete upstream test suite.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import textwrap
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "python_repo_fixtures"


def case(request, expected):
    return {"request": request, "expected": expected}


def document(identifier, **fields):
    return {"id": identifier, "data": fields}


def tiny_cases():
    cases = []
    def add(steps, results, backend="memory"):
        cases.append(case({"backend": backend, "steps": steps}, {"results": results}))
    add([{"op": "insert_doc", "id": 10, "data": {"x": 1}}, {"op": "insert", "data": {"x": 2}}, {"op": "all"}],
        [10, 11, [document(10, x=1), document(11, x=2)]])
    add([{"op": "insert_doc", "id": 3, "data": {"x": 1}}, {"op": "upsert_doc", "id": 3, "data": {"y": 2}}, {"op": "get", "id": 3}],
        [3, [3], document(3, x=1, y=2)])
    add([{"op": "insert", "data": {"name": "ALICE", "active": True}}, {"op": "search", "query": {"op": "lower_eq", "path": ["name"], "value": "alice"}}],
        [1, [document(1, name="ALICE", active=True)]])
    add([{"op": "insert", "data": {"x": 1}}, {"op": "search", "query": {"op": "fragment", "value": {"x": 1}}}, {"op": "get_many", "ids": [1]}],
        [1, [document(1, x=1)], [document(1, x=1)]])
    # Public regression: persistence through the real JSON storage and caching middleware.
    add([{"op": "insert", "data": {"x": 9}}, {"op": "reopen"}, {"op": "all"}], [1, True, [document(1, x=9)]], "cached")
    public_count = len(cases)
    for backend in ["memory", "json", "cached"]:
        add([{"op": "bulk", "documents": [{"id": 7, "data": {"v": "a"}}, {"data": {"v": "b"}}, {"id": 30, "data": {"v": "c"}}]},
             {"op": "insert", "data": {"v": "d"}}, {"op": "all"}],
            [[7, 8, 30], 31, [document(7, v="a"), document(8, v="b"), document(30, v="c"), document(31, v="d")]], backend)
        add([{"op": "insert_doc", "id": 5, "data": {"x": 1}}, {"op": "insert_doc", "id": 5, "data": {"x": 99}}, {"op": "all"}],
            [5, {"error": "ValueError"}, [document(5, x=1)]], backend)
        add([{"op": "upsert_doc", "id": 40, "data": {"a": 1}}, {"op": "upsert_doc", "id": 40, "data": {"b": 2}},
             {"op": "insert", "data": {"a": 3}}, {"op": "all"}],
            [[40], [40], 41, [document(40, a=1, b=2), document(41, a=3)]], backend)
        add([{"op": "bulk", "documents": [{"data": {"x": 1}}, {"data": {"x": 2}}, {"data": {"x": 3}}]},
             {"op": "get_many", "ids": [3, 1, 3, 999]}, {"op": "get_many", "ids": []}],
            [[1, 2, 3], [document(1, x=1), document(3, x=3)], []], backend)
        add([{"op": "insert_doc", "id": 9, "data": {"n": 4}}, {"op": "insert_doc", "id": 9, "data": {"n": 8}, "table": "other"},
             {"op": "all"}, {"op": "all", "table": "other"}],
            [9, 9, [document(9, n=4)], [document(9, n=8)]], backend)
        rows = [{"score": 1}, {"score": 5}, {"score": 9}]
        add([{"op": "bulk", "documents": [{"data": x} for x in rows]},
             {"op": "dynamic_map", "field": "score", "first": 0, "second": 10, "threshold": 8}],
            [[1, 2, 3], [[document(3, score=9)], [document(i + 1, **r) for i, r in enumerate(rows)]]], backend)
        q = {"op": "eq", "path": ["active"], "value": True}
        add([{"op": "bulk", "documents": [{"data": {"active": True, "x": 1}}, {"data": {"active": False, "x": 2}}]},
             {"op": "search", "query": q}, {"op": "update", "query": q, "data": {"active": False}}, {"op": "search", "query": q},
             {"op": "upsert_query", "query": q, "data": {"active": True, "x": 3}}, {"op": "search", "query": q}],
            [[1, 2], [document(1, active=True, x=1)], [1], [], [3], [document(3, active=True, x=3)]], backend)
    add([{"op": "bulk", "documents": [{"data": {"profile": {"team": "a", "level": 2}}}, {"data": {"profile": {"team": "b"}}}, {"data": {"other": 1}}]},
         {"op": "search", "query": {"op": "fragment", "path": ["profile"], "value": {"team": "a"}}}],
        [[1, 2, 3], [document(1, profile={"team": "a", "level": 2})]])
    for number in [2, 17, 101]:
        add([{"op": "insert_doc", "id": number, "data": {"x": 1}}, {"op": "remove", "query": {"op": "noop"}},
             {"op": "insert_doc", "id": number, "data": {"x": 2}}, {"op": "get", "id": number}],
            [number, [number], number, document(number, x=2)])
    return cases[:public_count], cases


def signing_cases():
    cases = []
    def rotation(keys, payload, serializer="url"):
        return case({"mode": "rotate", "keys": keys, "payload": payload, "serializer": serializer},
                    {"legacy_values": [payload] * len(keys), "current": payload, "newest_accepts": True,
                     "old_accepts": [False] * (len(keys) - 1), "wrong_salt_rejected": True, "tamper_rejected": True})
    def timed(age, max_age, keys, serializer="url_timed", payload=None):
        payload = {"id": 1} if payload is None else payload
        failed = max_age is not None and (age < 0 or age > max_age)
        result = {"error": "SignatureExpired", "timestamp_utc": True} if failed else {
            "value": payload, "timestamp_utc": True, "timestamp_seconds": 1700000000}
        return case({"mode": "timed", "keys": keys, "signed_at": 1700000000, "now": 1700000000 + age,
                     "max_age": max_age, "serializer": serializer, "payload": payload}, result)
    cases.append(rotation(["retired", "current"], {"user": "alice"}))
    cases.append(rotation(["one-key"], [1, "two"], "plain"))
    cases.append(timed(10, 20, ["retired", "current"]))
    cases.append(timed(21, 20, ["one-key"], "timed"))
    public_count = len(cases)
    for serializer in ["plain", "url", "timed", "url_timed"]:
        for keys, payload in [(["a", "b", "c"], {"nested": [False, None, {"x": 7}]}),
                              (["old", "new"], "repeat-" * 150), (["only"], {})]:
            cases.append(rotation(keys, payload, serializer))
        payload = {"v": 9}
        cases.append(case({"mode": "fallback", "keys": ["retired", "current"], "serializer": serializer, "payload": payload},
                          {"legacy_value": payload, "current_value": payload, "old_digest_rejected_without_fallback": True,
                           "current_accepted_by_newest": True}))
    for serializer in ["timed", "url_timed"]:
        for age, maximum in [(0, 0), (20, 20), (21, 20), (-1, 20), (100000, None), (-5, None)]:
            cases.append(timed(age, maximum, ["retired", "current", "newest"], serializer))
    for keys, message in [(["a", "b", "c"], "hello"), (["one"], ""), (["old", "new"], "spaces and punctuation !")]:
        cases.append(case({"mode": "signer", "keys": keys, "message": message},
                          {"value": message, "legacy_valid": [True] * len(keys), "newest_valid": True,
                           "old_valid": [False] * (len(keys) - 1), "other_valid": False}))
    return cases[:public_count], cases


CHECK = '''from copy import deepcopy
import json
import os
from pathlib import Path
from check_client import load_submission

cases = json.loads(CASES_LITERAL)
submission = load_submission(Path(os.environ["LAB_WORKSPACE"]) / "app.py")
failures = []
for index, item in enumerate(cases, 1):
    try:
        request = deepcopy(item["request"])
        actual = submission.run(request)
        assert actual == item["expected"], f"expected {item['expected']!r}, got {actual!r}"
    except Exception as exc:
        failures.append(f"case {index}: {str(exc)[:1200]}")
print(f"Passed {len(cases) - len(failures)}/{len(cases)} repository scenarios", flush=True)
assert not failures, "\\n".join(failures)
'''


TASKS = [
    {"id": "python-tinydb-upgrade", "repo": "msiemens/tinydb", "baseline": "v4.0.0", "reference": "v4.8.0", "package": "tinydb",
     "adapter": "tinydb_app.py", "title": "Upgrade document identity and composable queries in TinyDB",
     "description": "在真实 TinyDB 代码库中扩展显式文档 ID、批量读取和可组合查询，保持查询缓存、存储和多表行为一致。不要只在适配器中实现一个新数据库；必须修改 tinydb 包本身。",
     "acceptance": [
         "Document(data, doc_id=ID) 在 insert/insert_multiple 中使用指定整数 ID；自动 ID 按当前最大 ID 加一分配，显式 ID 后不能碰撞。重复 ID 抛 ValueError，原文档不覆盖；空表从1开始。批量输入可为迭代器，返回各文档 ID。",
         "upsert(Document(...)) 不要求查询条件：存在时合并字段，不存在时按该 ID 插入；返回影响的 ID 列表。原 upsert(mapping, query)、普通 insert/update/remove/get/search 保持可用。",
         "get(doc_ids=[...]) 返回实际存在的 Document 列表，按表内存储顺序排列，忽略重复和缺失 ID，空列表返回空列表。单 ID get 不变。不同表的 ID 空间与数据独立。",
         "Query().fragment(mapping) 与嵌套字段 fragment 匹配给出的键值子集；缺失字段不匹配。Query().noop() 永远为真，可与 AND/OR/NOT 组合。现有 eq/ge/exists/one_of 查询保持可用。",
         "Query.field.map(fn) 将函数加入访问路径后再比较；不存在或不适用的字段不匹配。含可变函数的查询不得复用过时缓存：同一 Query 的闭包状态改变后搜索应重新求值。普通查询在 update/remove/upsert 后也不得返回旧结果。",
         "以上行为在 MemoryStorage、JSONStorage 和 CachingMiddleware(JSONStorage) 一致；关闭并重开文件数据库保留数据。Document 元数据不能写进用户字段。read-only app.py 定义输入操作与输出格式，tests_lab 公开场景可阅读；不要求特定内部实现。"],
     "cases": tiny_cases},
    {"id": "python-itsdangerous-upgrade", "repo": "pallets/itsdangerous", "baseline": "1.1.0", "reference": "2.2.0", "package": "src/itsdangerous",
     "adapter": "itsdangerous_app.py", "title": "Upgrade key rotation and timed validation in ItsDangerous",
     "description": "在真实 ItsDangerous 代码库中支持密钥轮换及一致的时间有效性验证，贯通签名器、序列化器、时间签名和 URL-safe 组合；保持已有单密钥数据可验证。修改包本身，不能修改只读适配器或验收。",
     "acceptance": [
         "Signer、Serializer、TimedSerializer、URLSafeSerializer、URLSafeTimedSerializer 的 secret_key 接受一个密钥，或按旧到新排列的非空密钥列表。新签名只使用最后一个密钥，验签接受列表中任意密钥；单密钥调用保持兼容。",
         "旧密钥单独生成的 token 在轮换列表中可读；轮换生成的新 token 仅最新密钥可验证。直接 Signer 与四种 Serializer 都遵循该规则，支持 JSON 标量、列表、嵌套对象和可压缩长字符串。",
         "salt 必须继续隔离用途；错误密钥、错误 salt、被篡改签名不得通过验证。不得禁用或绕过签名检查。",
         "signer_kwargs 指定新摘要算法时，fallback_signers 允许仅在验证时回退旧摘要与任意旧密钥；新签名仍使用新摘要与最新密钥。显式 fallback_signers=[] 不接受旧摘要签名。",
         "时间验证使用 now-signed_at；给定 max_age 时，年龄等于上限有效，大于上限或年龄为负均抛 SignatureExpired；max_age=None 时不限制年龄。max_age=0 只能接受同一秒。",
         "return_timestamp=True 返回的时间戳，以及 SignatureExpired.date_signed，都必须是 UTC aware datetime，并表示原签名时间。时间行为在 TimedSerializer 和 URLSafeTimedSerializer 中一致，可与轮换和摘要回退组合。app.py 用虚拟时钟检查边界，不需要等待或网络。"],
     "cases": signing_cases},
]


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def prepare(suite, download=False):
    if suite.exists():
        raise ValueError("Refusing to overwrite an existing suite")
    sources = json.loads((FIXTURES / "sources.json").read_text(encoding="utf-8"))
    contents = {}
    for source in sources:
        archive = ROOT / source["archive"].replace("\\", "/")
        if not archive.exists():
            if not download:
                raise ValueError("Missing cached archive; use --download")
            archive.parent.mkdir(parents=True, exist_ok=True)
            url = f"https://codeload.github.com/{source['repo']}/zip/{source['commit']}"
            with urllib.request.urlopen(url, timeout=60) as response:
                archive.write_bytes(response.read())
        if hashlib.sha256(archive.read_bytes()).hexdigest() != source["sha256"]:
            raise ValueError("Upstream archive checksum mismatch")
        with zipfile.ZipFile(archive) as zipped:
            prefix = zipped.namelist()[0].split("/")[0] + "/"
            files = {}
            for member in zipped.namelist():
                relative = member[len(prefix):]
                if not relative or member.endswith("/") or any(part.startswith(".") for part in Path(relative).parts):
                    continue
                if Path(relative).suffix not in {".py", ".rst", ".md", ".txt", ".toml", ".cfg", ".ini", ".typed", ""}:
                    continue
                files[relative] = zipped.read(member).decode("utf-8")
            contents[(source["repo"], source["ref"])] = files
    manifest = {"schema_version": 1, "id": "pure-python-repos-v1", "split": "development",
                "provenance": "Real upstream source; manually curated historical upgrade contracts and custom standard-library acceptance, not official benchmark or original issues.",
                "sources": sources, "tasks": []}
    for item in TASKS:
        folder = suite / "tasks" / item["id"]
        baseline = contents[(item["repo"], item["baseline"])]
        target = dict(contents[(item["repo"], item["reference"])])
        if item["id"] == "python-tinydb-upgrade":
            # Independent acceptance found an upstream 4.8.0 edge case: a mixed
            # explicit/automatic-ID batch allocates from persisted, not pending,
            # rows. Our declared contract requires a coherent ID space.
            name = "tinydb/table.py"
            text = target[name]
            start, end = text.index("    def insert_multiple("), text.index("    def all(")
            block = text[start:end]
            block = block.replace("if document.doc_id in table:", "if str(document.doc_id) in table:")
            block = block.replace("table[doc_id] = dict(document)", "table[str(doc_id)] = dict(document)")
            block = block.replace("doc_id = self._get_next_id()", "doc_id = max((int(key) for key in table), default=0) + 1")
            block = block.replace("self._update_table(updater)", "self._update_table(updater)\n        self._next_id = None")
            target[name] = text[:start] + block + text[end:]
        package = item["package"] + "/"
        editable = sorted({name for tree in [baseline, target] for name in tree if name.startswith(package) and name.endswith(".py")})
        for name, text in baseline.items():
            write(folder / "source" / name, text)
        for name in editable:
            if name not in baseline:
                write(folder / "source" / name, "# Reserved module for this upgrade.\n")
            write(folder / "operator/reference" / name, target.get(name, baseline.get(name, "")))
        for name, text in target.items():
            if "/" not in name and name.upper().startswith("LICENSE"):
                write(folder / "operator/reference-license" / name, text)
        write(folder / "source/app.py", (FIXTURES / item["adapter"]).read_text(encoding="utf-8"))
        write(folder / "source/LAB_TASK.md", item["title"] + "\n\n" + item["description"] + "\n\n" + "\n".join(item["acceptance"]) +
              "\n\nUse read_file_chunk for long files and edit_file for unique literal replacements. Existing upstream pytest tests are included for reading; the supported lab checks use only the Python standard library.\n")
        public, final = item["cases"]()
        task = {"schema_version": 1, "id": item["id"], "description": item["description"] + " 阅读 LAB_TASK.md 和只读 app.py，保持其外部协议。",
                "acceptance": item["acceptance"], "source_dir": "source", "editable_files": editable,
                "public_check": "public_check.py", "final_check": "final_check.py"}
        write(folder / "task.json", json.dumps(task, ensure_ascii=False, indent=2) + "\n")
        for kind, cases in [("public", public), ("final", final)]:
            text = CHECK.replace("CASES_LITERAL", repr(json.dumps(cases, ensure_ascii=True)))
            write(folder / (kind + "_check.py"), text)
        smoke = "import unittest\nfrom app import run\nimport json\nCASES = json.loads(" + repr(json.dumps(public)) + ")\n\nclass Smoke(unittest.TestCase):\n    def test_public_scenarios(self):\n        for item in CASES:\n            with self.subTest(request=item['request']):\n                self.assertEqual(run(item['request']), item['expected'])\n"
        write(folder / "source/tests_lab/test_public.py", smoke)
        # Deliberately incomplete fixes that pass public cases but fail held-out boundaries.
        if item["id"] == "python-tinydb-upgrade":
            name = "tinydb/table.py"
            original = target[name]
            needle = "doc_ids_set = set(str(doc_id) for doc_id in doc_ids)"
            if original.count(needle) != 1:
                raise ValueError("Partial control anchor changed")
            mutant = {name: original.replace(needle, "doc_ids_set = set(str(doc_id) for doc_id in doc_ids[:1])")}
        else:
            name = "src/itsdangerous/timed.py"
            original = target[name]
            needle = "if age < 0:"
            if original.count(needle) != 1:
                raise ValueError("Partial control anchor changed")
            mutant = {name: original.replace(needle, "if age < -999999:")}
        write(folder / "operator/mutants/public-only.json", json.dumps(mutant, indent=2) + "\n")
        entries = list((folder / "source").rglob("*"))
        source_py = [p for p in entries if p.is_file() and p.suffix == ".py" and p.relative_to(folder / "source").as_posix().startswith(package)]
        row = {"id": item["id"], "manifest": "tasks/" + item["id"] + "/task.json", "repo": item["repo"],
               "baseline": item["baseline"], "reference": item["reference"], "difficulty": "unmeasured",
               "editable_files": len(editable), "package_python_lines": sum(len(p.read_text(encoding="utf-8").splitlines()) for p in source_py),
               "readable_files": sum(p.is_file() for p in entries), "public_scenarios": len(public), "final_scenarios": len(final)}
        manifest["tasks"].append(row)
        print(json.dumps(row, ensure_ascii=True), flush=True)
    write(suite / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks/pure-python-repos-v1")
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    prepare(args.output.resolve(), args.download)
