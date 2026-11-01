"""Build six original, offline repository tasks; no model or network calls.

Do not overwrite an existing suite. Reference patches and negative controls live
outside task source directories and are never part of an agent's file allowlist.
"""
from copy import deepcopy
import base64
import json
from pathlib import Path
import random
import textwrap

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / "benchmarks/repo-workflows-v1"


def code(text):
    return textwrap.dedent(text).lstrip("\n")


def case(request, expected):
    return {"request": request, "expected": expected}


TASKS = []

# Local repair 1: preserve an existing HTTP response contract.
paging_fixed = code('''
    def paginate(items, page=1, page_size=20):
        if type(page) is not int or type(page_size) is not int or page < 1 or page_size < 1:
            raise ValueError("invalid pagination")
        total = len(items)
        start = (page - 1) * page_size
        total_pages = (total + page_size - 1) // page_size
        return {"items": items[start:start + page_size], "page": page, "page_size": page_size,
                "total": total, "total_pages": total_pages, "has_next": page < total_pages}
''')


def page_expected(items, page=1, size=20):
    pages, remainder = divmod(len(items), size)
    pages += bool(remainder)
    selected = [value for index, value in enumerate(items) if (page - 1) * size <= index < page * size]
    return {"items": selected, "page": page, "page_size": size, "total": len(items),
            "total_pages": pages, "has_next": page < pages}


paging_public = [case({"items": [1, 2, 3, 4], "page_size": 2}, page_expected([1, 2, 3, 4], 1, 2)),
                 case({"items": []}, page_expected([])),
                 case({"items": [1], "page": 0}, {"error": "invalid_pagination"})]
paging_hidden = []
for n, size, page in [(1, 1, 1), (5, 2, 1), (5, 2, 3), (5, 2, 4), (6, 3, 2), (6, 3, 3),
                      (0, 3, 1), (19, 5, 4), (17, 100, 1), (50, 7, 7)]:
    values = [{"id": i, "name": "item-" + str(i)} for i in range(n)]
    paging_hidden.append(case({"items": values, "page": page, "page_size": size}, page_expected(values, page, size)))
for field, value in [("page", True), ("page", 1.5), ("page", "1"), ("page_size", 0),
                     ("page_size", -1), ("page_size", False), ("page_size", 2.0)]:
    paging_hidden.append(case({"items": [3, 4], field: value}, {"error": "invalid_pagination"}))
TASKS.append({"id": "repo-page-boundaries", "category": "local-repair", "title": "修复分页 API 的边界与元数据",
    "description": "分页接口出现每页少一条、末页页数不一致的问题。请修复已有分页组件，保持 API 返回结构和错误格式，检查空集合、最后一页及非法参数。",
    "acceptance": ["run(request) 接收 items（必填列表）、page（默认1）、page_size（默认20）；不修改请求数据。",
        "page/page_size 必须为正整数，bool、字符串、浮点数无效；无效返回 {error: invalid_pagination}。",
        "返回 items/page/page_size/total/total_pages/has_next；total_pages 向上取整，空集合为0。",
        "越过最后一页返回空 items；has_next 仅表示当前页之后还有数据。"],
    "files": {"workshop/paging.py": paging_fixed.replace("start + page_size]", "start + page_size - 1]").replace("(total + page_size - 1) // page_size", "total // page_size"),
        "workshop/service.py": code('''
            from workshop.paging import paginate
            def run(request):
                try:
                    return paginate(request["items"], request.get("page", 1), request.get("page_size", 20))
                except ValueError:
                    return {"error": "invalid_pagination"}
        ''')},
    "reference": {"workshop/paging.py": paging_fixed},
    "partial": {"workshop/paging.py": paging_fixed.replace('"has_next": page < total_pages', '"has_next": bool(items[start:start + page_size])')},
    "public": paging_public, "hidden": paging_hidden})

# Local repair 2: deterministic transport + virtual clock, no real sleeping.
retry_fixed = code('''
    from math import isfinite
    def execute(transport, clock, max_attempts, base_delay):
        if type(max_attempts) is not int or max_attempts < 1:
            raise ValueError("invalid attempts")
        if type(base_delay) not in (int, float) or not isfinite(base_delay) or base_delay < 0:
            raise ValueError("invalid delay")
        retryable = {429, 500, 502, 503, 504}
        for attempt in range(1, max_attempts + 1):
            result = transport.send()
            if result["status"] not in retryable or attempt == max_attempts:
                return result
            hint = result.get("retry_after")
            delay = hint if type(hint) in (int, float) and hint >= 0 else base_delay * 2 ** (attempt - 1)
            clock.sleep(delay)
''')


def retry_case(responses, attempts, delay, expected_status, expected_delays, calls, body=None):
    return case({"responses": responses, "max_attempts": attempts, "base_delay": delay},
                {"status": expected_status, "body": body, "attempts": calls, "delays": expected_delays})


retry_public = [retry_case([{"status": 503}, {"status": 200, "body": "ok"}], 3, 1, 200, [1], 2, "ok"),
                retry_case([{"status": 404}], 3, 1, 404, [], 1),
                retry_case([{"status": 500}], 1, 2, 500, [], 1)]
retry_hidden = [retry_case([{"status": 429, "retry_after": 0}, {"status": 200}], 3, 5, 200, [0], 2),
    retry_case([{"status": 503, "retry_after": 2.5}, {"status": 200}], 2, 1, 200, [2.5], 2),
    retry_case([{"status": 502}, {"status": 503}, {"status": 204}], 4, 0.5, 204, [0.5, 1], 3),
    retry_case([{"status": 500}], 3, 2, 500, [2, 4], 3),
    retry_case([{"status": 200, "body": {"id": 9}}], 4, 10, 200, [], 1, {"id": 9}),
    retry_case([{"status": 429, "retry_after": -2}, {"status": 200}], 2, 3, 200, [3], 2),
    retry_case([{"status": 503, "retry_after": "2"}, {"status": 200}], 2, 3, 200, [3], 2),
    retry_case([{"status": 503, "retry_after": True}, {"status": 200}], 2, 3, 200, [3], 2)]
for status in [400, 401, 403, 408, 418, 501, 505, 302]:
    retry_hidden.append(retry_case([{"status": status}], 4, 1, status, [], 1))
for value in [0, -1, True, 1.5]:
    retry_hidden.append(case({"responses": [{"status": 200}], "max_attempts": value}, {"error": "invalid_retry_options"}))
for value in [-1, True, "1", None]:
    retry_hidden.append(case({"responses": [{"status": 200}], "base_delay": value}, {"error": "invalid_retry_options"}))
retry_hidden.extend([retry_case([{"status": 500}, {"status": 200}], 2, 0, 200, [0], 2),
    case({"responses": [{"status": 503}, {"status": 200}]}, {"status": 200, "body": None, "attempts": 2, "delays": [1]}),
    case({"responses": [{"status": 500}]}, {"status": 500, "body": None, "attempts": 3, "delays": [1, 2]})])
TASKS.append({"id": "repo-retry-policy", "category": "local-repair", "title": "修复 HTTP 重试的次数与等待策略",
    "description": "HTTP 客户端会对永久错误反复重试，重试耗尽后仍然等待。请修复现有重试策略，保持 transport 与虚拟 clock 的接口。",
    "acceptance": ["run(request) 接收非空 responses 列表、max_attempts（默认3）、base_delay（默认1），返回 status/body/attempts/delays；不修改输入。",
        "仅 429/500/502/503/504 可重试；max_attempts 包含第一次请求，必须为正整数且不接受 bool；base_delay 为非负有限数字且不接受 bool；无效返回 {error: invalid_retry_options}。",
        "第n次失败后的默认等待为 base_delay * 2**(n-1)；非负数值 retry_after 优先（包括0）；其他 retry_after 忽略。",
        "成功、永久错误、最后一次尝试之后均不等待。响应列表不足时 transport 重复最后一个响应；body 缺失时为null。无需真实网络或睡眠。"],
    "files": {"workshop/retry.py": retry_fixed.replace('retryable = {429, 500, 502, 503, 504}', 'retryable = set(range(400, 600))').replace('if result["status"] not in retryable or attempt == max_attempts:', 'if result["status"] not in retryable:').replace('clock.sleep(delay)', 'clock.sleep(delay)\n        return result'),
        "workshop/transport.py": code('''
            from copy import deepcopy
            class Transport:
                def __init__(self, responses):
                    self.responses = deepcopy(responses)
                    self.attempts = 0
                def send(self):
                    index = min(self.attempts, len(self.responses) - 1)
                    self.attempts += 1
                    return self.responses[index]
        '''),
        "workshop/clock.py": code('''
            class Clock:
                def __init__(self):
                    self.delays = []
                def sleep(self, seconds):
                    self.delays.append(seconds)
        '''),
        "workshop/service.py": code('''
            from workshop.transport import Transport
            from workshop.clock import Clock
            from workshop.retry import execute
            def run(request):
                transport, clock = Transport(request["responses"]), Clock()
                try:
                    result = execute(transport, clock, request.get("max_attempts", 3), request.get("base_delay", 1))
                except ValueError:
                    return {"error": "invalid_retry_options"}
                return {"status": result["status"], "body": result.get("body"), "attempts": transport.attempts, "delays": clock.delays}
        ''')},
    "reference": {"workshop/retry.py": retry_fixed},
    "partial": {"workshop/retry.py": retry_fixed.replace('hint >= 0', 'hint > 0')},
    "public": retry_public, "hidden": retry_hidden})

# Cross-file change 1: parsing, precedence, conversion and presentation.
settings_fixed = code('''
    from workshop.defaults import DEFAULT_TIMEOUT_MS
    def load(config, env, cli):
        if cli.get("timeout_ms") is not None:
            value = cli["timeout_ms"]
        elif "APP_TIMEOUT_MS" in env:
            value = env["APP_TIMEOUT_MS"]
        else:
            value = config.get("timeout_ms", DEFAULT_TIMEOUT_MS)
        if type(value) is str:
            value = value.strip()
            if not value or any(c not in "0123456789" for c in value):
                raise ValueError("invalid timeout")
            value = int(value)
        if type(value) is not int or value < 0:
            raise ValueError("invalid timeout")
        return {"timeout_ms": value}
''')
cli_fixed = code('''
    import argparse
    def parse(argv):
        parser = argparse.ArgumentParser()
        parser.add_argument("--target", default="status")
        parser.add_argument("--timeout-ms", default=None)
        return vars(parser.parse_args(argv))
''')
transport_fixed = code('''
    def build_request(target, settings):
        timeout = settings["timeout_ms"]
        return {"target": target, "timeout_ms": timeout,
                "timeout_seconds": None if timeout == 0 else timeout / 1000,
                "headers": {"User-Agent": "lab-client/1"}}
''')
timeout_service = code('''
    from workshop.cli import parse
    from workshop.settings import load
    from workshop.transport import build_request
    def run(request):
        options = parse(request.get("argv", []))
        try:
            settings = load(request.get("config", {}), request.get("env", {}), options)
        except ValueError:
            return {"error": "invalid_timeout"}
        return build_request(options["target"], settings)
''')


def timeout_expected(value, target="status"):
    return {"target": target, "timeout_ms": value, "timeout_seconds": None if value == 0 else value / 1000,
            "headers": {"User-Agent": "lab-client/1"}}


timeout_public = [case({}, timeout_expected(1000)),
    case({"argv": ["--timeout-ms", "250", "--target", "health"], "config": {"timeout_ms": 99}}, timeout_expected(250, "health")),
    case({"argv": ["--timeout-ms", "0"]}, timeout_expected(0))]
timeout_hidden = [case({"config": {"timeout_ms": 400}}, timeout_expected(400)),
    case({"env": {"APP_TIMEOUT_MS": "75"}, "config": {"timeout_ms": 900}}, timeout_expected(75)),
    case({"argv": ["--timeout-ms", "10"], "env": {"APP_TIMEOUT_MS": "20"}, "config": {"timeout_ms": 30}}, timeout_expected(10)),
    case({"env": {"APP_TIMEOUT_MS": "0"}}, timeout_expected(0)),
    case({"config": {"timeout_ms": " 1250 "}}, timeout_expected(1250)),
    case({"argv": ["--target", "metrics"]}, timeout_expected(1000, "metrics"))]
for invalid in [-1, True, 2.5, "", "2.5", "+3", "-2", None]:
    timeout_hidden.append(case({"config": {"timeout_ms": invalid}}, {"error": "invalid_timeout"}))
for invalid in ["", "-3", "bad"]:
    timeout_hidden.append(case({"env": {"APP_TIMEOUT_MS": invalid}, "config": {"timeout_ms": 200}}, {"error": "invalid_timeout"}))
timeout_hidden.extend([case({"config": {"timeout_ms": 0}}, timeout_expected(0)),
    case({"argv": ["--timeout-ms", "10"], "env": {"APP_TIMEOUT_MS": "bad"}}, timeout_expected(10)),
    case({"env": {"APP_TIMEOUT_MS": "20"}, "config": {"timeout_ms": None}}, timeout_expected(20)),
    case({"argv": ["--timeout-ms", "-1"]}, {"error": "invalid_timeout"})])
TASKS.append({"id": "repo-timeout-wiring", "category": "cross-file-change", "title": "贯通命令行、配置与传输层的超时设置",
    "description": "给已有客户端增加 --timeout-ms 与 APP_TIMEOUT_MS 支持，确保配置选择、毫秒转换及请求展示贯通，保留 --target、User-Agent 和原有默认行为。",
    "acceptance": ["run(request) 接收 argv/config/env（默认空）；不修改输入。argv 仅含已声明的 --target 与 --timeout-ms，不要求支持其他命令。",
        "timeout_ms 优先级为 CLI > APP_TIMEOUT_MS 环境映射 > config.timeout_ms > 默认1000；选中高优先级无效值必须报错，不退回低优先级。",
        "各来源接受非负整数或去除两端空白后的ASCII十进制数字字符串；bool/浮点/null/负数/空字符串无效，返回 {error: invalid_timeout}。",
        "0 表示禁用超时，传输层 timeout_seconds 为null；否则毫秒除以1000。返回 target/timeout_ms/timeout_seconds/headers，保留 User-Agent: lab-client/1。"],
    "files": {"workshop/defaults.py": "DEFAULT_TIMEOUT_MS = 1000\n",
        "workshop/cli.py": cli_fixed.replace('        parser.add_argument("--timeout-ms", default=None)\n', '').replace('    parser.add_argument("--timeout-ms", default=None)\n', ''),
        "workshop/settings.py": code('''
            from workshop.defaults import DEFAULT_TIMEOUT_MS
            def load(config, env, cli):
                return {"timeout_ms": config.get("timeout_ms") or DEFAULT_TIMEOUT_MS}
        '''),
        "workshop/transport.py": transport_fixed.replace('timeout = settings["timeout_ms"]', 'timeout = 1000'),
        "workshop/service.py": timeout_service.replace('request.get("env", {}), options', 'request.get("env", {}), {}')},
    "reference": {"workshop/cli.py": cli_fixed, "workshop/settings.py": settings_fixed,
                  "workshop/transport.py": transport_fixed, "workshop/service.py": timeout_service},
    "partial": {"workshop/settings.py": settings_fixed.replace('elif "APP_TIMEOUT_MS" in env:', 'elif False:')},
    "public": timeout_public, "hidden": timeout_hidden})

# Cross-file change 2: preserve data across delete, restore and create operations.
notes_repo = code('''
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
            self.notes[key]["deleted"] = True
            return True
        def restore(self, key):
            if key not in self.notes:
                return False
            self.notes[key]["deleted"] = False
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
''')
notes_views = code('''
    def present(note):
        return {"id": note["id"], "text": note["text"], "deleted": note["deleted"]}
''')
notes_service = code('''
    from workshop.repository import Repository
    from workshop.views import present
    def run(request):
        repo = Repository(request.get("notes", []))
        results = []
        for operation in request.get("operations", []):
            action = operation["op"]
            if action == "list":
                results.append([present(n) for n in repo.list(operation.get("include_deleted", False))])
            elif action == "get":
                note = repo.get(operation["id"], operation.get("include_deleted", False))
                results.append(present(note) if note is not None else {"error": "not_found"})
            elif action in ("delete", "restore"):
                ok = getattr(repo, action)(operation["id"])
                results.append({"ok": True} if ok else {"error": "not_found"})
            elif action == "create":
                note = repo.create(operation["id"], operation["text"])
                results.append(present(note) if note is not None else {"error": "conflict"})
            elif action == "update":
                note = repo.update(operation["id"], operation["text"])
                results.append(present(note) if note is not None else {"error": "not_found"})
            else:
                raise ValueError("unsupported operation")
        return {"results": results}
''')


def note(key, text, deleted=False):
    return {"id": key, "text": text, "deleted": deleted}


def notes_case(initial, operations, results):
    return case({"notes": initial, "operations": operations}, {"results": results})


ok, missing, conflict = {"ok": True}, {"error": "not_found"}, {"error": "conflict"}
notes_public = [notes_case([{"id": "a", "text": "first"}], [{"op": "list"}], [[note("a", "first")]]),
    notes_case([{"id": "a", "text": "first"}], [{"op": "delete", "id": "a"}, {"op": "list"}], [ok, []]),
    notes_case([{"id": "a", "text": "first"}], [{"op": "delete", "id": "a"}, {"op": "restore", "id": "a"}, {"op": "get", "id": "a"}], [ok, ok, note("a", "first")])]
notes_hidden = [
    notes_case([{"id": "a", "text": "first"}], [{"op": "delete", "id": "a"}, {"op": "get", "id": "a"}, {"op": "get", "id": "a", "include_deleted": True}], [ok, missing, note("a", "first", True)]),
    notes_case([{"id": "a", "text": "first"}], [{"op": "delete", "id": "a"}, {"op": "delete", "id": "a"}, {"op": "create", "id": "a", "text": "replacement"}], [ok, ok, conflict]),
    notes_case([{"id": "a", "text": "first"}], [{"op": "delete", "id": "a"}, {"op": "update", "id": "a", "text": "bad"}, {"op": "restore", "id": "a"}, {"op": "get", "id": "a"}], [ok, missing, ok, note("a", "first")]),
    notes_case([], [{"op": "get", "id": "x"}, {"op": "delete", "id": "x"}, {"op": "restore", "id": "x"}, {"op": "update", "id": "x", "text": "bad"}], [missing, missing, missing, missing]),
    notes_case([note("b", "B", True), note("a", "A")], [{"op": "list"}, {"op": "list", "include_deleted": True}, {"op": "restore", "id": "b"}, {"op": "list"}], [[note("a", "A")], [note("b", "B", True), note("a", "A")], ok, [note("b", "B"), note("a", "A")]]),
    notes_case([], [{"op": "create", "id": "x", "text": "old"}, {"op": "update", "id": "x", "text": "new"}, {"op": "create", "id": "x", "text": "dup"}, {"op": "restore", "id": "x"}], [note("x", "old"), note("x", "new"), conflict, ok]),
    notes_case([note("a", "A"), note("b", "B"), note("c", "C")], [{"op": "delete", "id": "b"}, {"op": "create", "id": "d", "text": "D"}, {"op": "list"}, {"op": "list", "include_deleted": True}], [ok, note("d", "D"), [note("a", "A"), note("c", "C"), note("d", "D")], [note("a", "A"), note("b", "B", True), note("c", "C"), note("d", "D")]])]
notes_hidden.append(case({}, {"results": []}))
for index in range(5):
    key, text = "note-" + str(index), "正文-" + str(index)
    notes_hidden.append(notes_case([note(key, text)], [{"op": "update", "id": key, "text": text + "!"},
        {"op": "delete", "id": key}, {"op": "restore", "id": key}, {"op": "list"}],
        [note(key, text + "!"), ok, ok, [note(key, text + "!")]]))
TASKS.append({"id": "repo-note-soft-delete", "category": "cross-file-change", "title": "为笔记服务增加软删除与恢复",
    "description": "现有笔记服务会永久删除记录。增加软删除与恢复，并让列表、详情、创建冲突和更新行为保持一致，不丢失原始内容。",
    "acceptance": ["run(request) 接收 notes 和 operations（默认空），按顺序处理，返回 {results: [...]}；不修改输入。笔记 id 为唯一非空字符串，text 为字符串，初始 deleted 默认为false。",
        "支持 list/get/delete/restore/create/update；所有笔记展示包含 id/text/deleted，列表保持初始及创建的插入顺序。",
        "delete 只标记 deleted=true，重复删除仍返回 {ok:true}；restore 恢复原内容，对未删除记录也幂等成功。不存在返回 {error:not_found}。",
        "list/get 默认屏蔽已删除记录；显式 include_deleted=true 才展示。update 只能更新未删除记录。",
        "create 与任意已有 id（含已删除）冲突时返回 {error:conflict}；成功返回新笔记。update 成功返回更新后的笔记。"],
    "files": {"workshop/repository.py": notes_repo.replace('self.notes[key]["deleted"] = True', 'del self.notes[key]').replace('self.notes[key]["deleted"] = False', 'return False'),
        "workshop/views.py": notes_views.replace(', "deleted": note["deleted"]', ''),
        "workshop/service.py": notes_service.replace('repo.get(operation["id"], operation.get("include_deleted", False))', 'repo.get(operation["id"])')},
    "reference": {"workshop/repository.py": notes_repo, "workshop/service.py": notes_service, "workshop/views.py": notes_views},
    "partial": {"workshop/service.py": notes_service.replace('repo.get(operation["id"], operation.get("include_deleted", False))', 'repo.get(operation["id"], True)')},
    "public": notes_public, "hidden": notes_hidden})

# Diagnosis 1: tenant/role leakage and cached object aliasing, with efficiency checks.
cache_fixed = code('''
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
''')
documents_fixed = code('''
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
''')
cache_runner = code('''
    from copy import deepcopy
    from workshop.repository import Repository
    from workshop.cache import Cache
    from workshop.documents import Service
    def run(request):
        repo = Repository(request["documents"])
        service, results, last = Service(repo, Cache()), [], None
        for action in request["actions"]:
            if action["op"] == "read":
                last = service.read(action["tenant"], action["id"], action["role"])
                results.append(deepcopy(last))
            elif action["op"] == "mutate_last":
                last[action["field"]] = action["value"]
                results.append({"ok": True})
            elif action["op"] == "update":
                service.update(action["tenant"], action["id"], action["title"])
                results.append({"ok": True})
        return {"results": results, "repository_reads": repo.reads}
''')


DOCS = [{"tenant": "a", "id": "1", "title": "Alpha", "secret": "a-secret"},
        {"tenant": "b", "id": "1", "title": "Beta", "secret": "b-secret"},
        {"tenant": "a", "id": "2", "title": "Other", "secret": "other-secret"}]


def read_action(tenant="a", key="1", role="viewer"):
    return {"op": "read", "tenant": tenant, "id": key, "role": role}


def view(title, key="1", secret=None):
    result = {"id": key, "title": title}
    if secret is not None:
        result["secret"] = secret
    return result


def cache_case(actions, results, reads, documents=None):
    return case({"documents": deepcopy(DOCS if documents is None else documents), "actions": actions},
                {"results": results, "repository_reads": reads})


cache_public = [cache_case([read_action()], [view("Alpha")], 1),
    cache_case([read_action(role="admin"), read_action()], [view("Alpha", secret="a-secret"), view("Alpha")], 2),
    cache_case([read_action(), read_action("b")], [view("Alpha"), view("Beta")], 2)]
cache_hidden = [cache_case([read_action(), read_action(), read_action()], [view("Alpha")] * 3, 1),
    cache_case([read_action(), {"op": "mutate_last", "field": "title", "value": "corrupt"}, read_action()], [view("Alpha"), ok, view("Alpha")], 1),
    cache_case([read_action(role="admin"), {"op": "mutate_last", "field": "secret", "value": "corrupt"}, read_action(role="admin")], [view("Alpha", secret="a-secret"), ok, view("Alpha", secret="a-secret")], 1),
    cache_case([read_action(), read_action(role="admin"), {"op": "update", "tenant": "a", "id": "1", "title": "New"}, read_action(), read_action(role="admin")], [view("Alpha"), view("Alpha", secret="a-secret"), ok, view("New"), view("New", secret="a-secret")], 4),
    cache_case([read_action(), read_action("b"), {"op": "update", "tenant": "a", "id": "1", "title": "New"}, read_action("b"), read_action()], [view("Alpha"), view("Beta"), ok, view("Beta"), view("New")], 3),
    cache_case([read_action(key="2"), {"op": "update", "tenant": "a", "id": "1", "title": "New"}, read_action(key="2")], [view("Other", "2"), ok, view("Other", "2")], 1)]
cache_hidden.append(cache_case([read_action(), read_action(role="admin"), read_action()],
    [view("Alpha"), view("Alpha", secret="a-secret"), view("Alpha")], 2))
for index in range(6):
    title, secret, key = "Doc-" + str(index), "Secret-" + str(index), str(10 + index)
    documents = [{"tenant": "team-" + str(index), "id": key, "title": title, "secret": secret}]
    action = read_action("team-" + str(index), key, "admin")
    cache_hidden.append(cache_case([action, action], [view(title, key, secret)] * 2, 1, documents))
TASKS.append({"id": "repo-cache-isolation", "category": "diagnosis", "title": "定位文档缓存的租户串数据与返回值污染",
    "description": "同编号文档在切换租户后偶尔显示错误标题；管理员先访问后，普通用户偶尔看到管理字段；调用方修改返回对象后，下一次读取也被污染。请定位并修复，保留有效缓存和局部失效。",
    "acceptance": ["run(request) 接收 documents 与 actions，返回 results 和实际 repository_reads；不修改请求。文档以 tenant/id 唯一，操作只涉及已存在文档，role 为 admin/viewer。",
        "read 返回 id/title，只有 admin 可见 secret；租户、文档、权限不同的结果不能混用。相同读取应命中缓存，不能直接关闭缓存。",
        "mutate_last 模拟调用方修改上次返回对象的 field/value，返回 {ok:true}，不应污染缓存或仓库；results 中保存的是各次调用当时的快照。",
        "update 只改指定 tenant/id 的 title，返回 {ok:true}；应失效该文档所有角色结果，其他文档与租户缓存保持有效。"],
    "files": {"workshop/cache.py": cache_fixed.replace('return deepcopy(self.entries.get(key))', 'return self.entries.get(key)').replace('self.entries[key] = deepcopy(value)', 'self.entries[key] = value').replace('if key[:2] == (tenant, doc_id):', 'if key == doc_id:'),
        "workshop/documents.py": documents_fixed.replace('key = (tenant, doc_id, role)', 'key = doc_id'),
        "workshop/render.py": code('''
            def present(document, role):
                result = {"id": document["id"], "title": document["title"]}
                if role == "admin":
                    result["secret"] = document["secret"]
                return result
        '''),
        "workshop/repository.py": code('''
            from copy import deepcopy
            class Repository:
                def __init__(self, documents):
                    self.documents = {(d["tenant"], d["id"]): deepcopy(d) for d in documents}
                    self.reads = 0
                def read(self, tenant, doc_id):
                    self.reads += 1
                    return deepcopy(self.documents[(tenant, doc_id)])
                def update(self, tenant, doc_id, title):
                    self.documents[(tenant, doc_id)]["title"] = title
        '''),
        "workshop/service.py": cache_runner},
    "reference": {"workshop/cache.py": cache_fixed, "workshop/documents.py": documents_fixed},
    "partial": {"workshop/cache.py": cache_fixed.replace('return deepcopy(self.entries.get(key))', 'return self.entries.get(key)').replace('self.entries[key] = deepcopy(value)', 'self.entries[key] = value')},
    "extra_mutants": {"disabled-cache": {"workshop/cache.py": cache_fixed.replace('return deepcopy(self.entries.get(key))', 'return None')}},
    "public": cache_public, "hidden": cache_hidden})

# Diagnosis 2: tied timestamps must not lose records between cursor pages.
tokens_source = code('''
    import base64
    import json
    def encode(marker):
        payload = {"v": 1, "ts": marker[0], "id": marker[1]}
        return base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    def decode(token):
        try:
            if type(token) is not str or not token:
                raise ValueError("invalid cursor")
            payload = json.loads(base64.b64decode(token + "=" * (-len(token) % 4), altchars=b"-_", validate=True))
            if (type(payload) is not dict or set(payload) != {"v", "ts", "id"}
                    or type(payload["v"]) is not int or payload["v"] != 1
                    or type(payload["ts"]) is not int or type(payload["id"]) is not int or payload["id"] < 1):
                raise ValueError("invalid cursor")
            return payload["ts"], payload["id"]
        except Exception as exc:
            raise ValueError("invalid cursor") from exc
''')
cursor_repo = code('''
    class Repository:
        def __init__(self, records):
            self.records = records
        def ordered(self):
            return sorted(self.records, key=lambda r: (r["created_at"], r["id"]))
''')
cursor_paging = code('''
    from workshop.tokens import encode
    def fetch(repository, limit, marker):
        rows = repository.ordered()
        if marker is not None:
            rows = [r for r in rows if (r["created_at"], r["id"]) > marker]
        page = rows[:limit]
        next_cursor = encode((page[-1]["created_at"], page[-1]["id"])) if len(rows) > len(page) else None
        return {"items": page, "next_cursor": next_cursor}
''')
cursor_service = code('''
    from workshop.repository import Repository
    from workshop.pagination import fetch
    from workshop.tokens import decode
    def run(request):
        limit = request.get("limit", 2)
        if type(limit) is not int or limit < 1:
            return {"error": "invalid_limit"}
        try:
            marker = decode(request["cursor"]) if request.get("cursor") is not None else None
        except ValueError:
            return {"error": "invalid_cursor"}
        return fetch(Repository(request["records"]), limit, marker)
''')


def encode_cursor(ts, key, version=1):
    value = json.dumps({"v": version, "ts": ts, "id": key}, separators=(",", ":"))
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def cursor_case(records, limit=2, marker=None):
    ordered = sorted(records, key=lambda r: (r["created_at"], r["id"]))
    eligible = [r for r in ordered if marker is None or (r["created_at"], r["id"]) > marker]
    selected = eligible[:limit]
    token = encode_cursor(selected[-1]["created_at"], selected[-1]["id"]) if len(eligible) > limit else None
    request = {"records": records, "limit": limit}
    if marker is not None:
        request["cursor"] = encode_cursor(*marker)
    return case(request, {"items": selected, "next_cursor": token})


EVENTS = [{"id": 2, "created_at": 1, "payload": "second"}, {"id": 1, "created_at": 1, "payload": "first"}, {"id": 3, "created_at": 2, "payload": "third"}]
cursor_public = [cursor_case(EVENTS), cursor_case(EVENTS, 2, (1, 1)), cursor_case([])]
cursor_hidden = [cursor_case(EVENTS, 3), cursor_case(EVENTS, 2, (1, 2)), cursor_case(EVENTS, 2, (2, 3)),
    cursor_case(EVENTS, 1), cursor_case(EVENTS, 100), cursor_case(EVENTS, 2, (0, 99))]
rng = random.Random(20261031)
for n in [1, 2, 6, 13, 20]:
    records = [{"id": i + 11, "created_at": i // 3 - 2, "payload": "event-" + str(i)} for i in range(n)]
    rng.shuffle(records)
    cursor_hidden.append(cursor_case(records, 2))
    cursor_hidden.append(cursor_case(records, 2, (records[0]["created_at"], records[0]["id"])))
for invalid in ["", "!", "e30", 23, encode_cursor(1, True), encode_cursor("1", 1), encode_cursor(1, 1, 2), encode_cursor(1, 0)]:
    cursor_hidden.append(case({"records": EVENTS, "cursor": invalid}, {"error": "invalid_cursor"}))
for invalid in [0, -1, True, 1.5, "2"]:
    cursor_hidden.append(case({"records": EVENTS, "limit": invalid}, {"error": "invalid_limit"}))
cursor_hidden.append(case({"records": EVENTS, "limit": 0, "cursor": "!"}, {"error": "invalid_limit"}))
TASKS.append({"id": "repo-cursor-pagination", "category": "diagnosis", "title": "定位相同时间戳下游标翻页的数据丢失",
    "description": "事件接口在相同 created_at 的记录之间翻页会丢数据或重复，无效游标还会静默从头开始。请定位排序、筛选和错误处理链路中的问题，保持既有游标格式。",
    "acceptance": ["run(request) 接收 records、limit（默认2）、cursor（默认null），不修改输入。每条记录 id 是唯一正整数、created_at 为整数，其余字段原样保留。",
        "按 (created_at,id) 升序分页，使用严格大于游标二元位置的记录；合法游标不要求对应现有记录。limit 为正整数且不接受 bool，否则返回 {error:invalid_limit}。",
        "返回 items 和 next_cursor；只有仍有后续记录时返回本页最后记录的游标，否则为null；空结果不得生成游标。",
        "沿用只读 tokens.py 的 v1 URL-safe Base64 JSON 格式；无效编码、字段或版本返回 {error:invalid_cursor}，不静默重置。先验证limit，再解析游标。"],
    "files": {"workshop/tokens.py": tokens_source,
        "workshop/repository.py": cursor_repo.replace('(r["created_at"], r["id"])', 'r["created_at"]'),
        "workshop/pagination.py": cursor_paging.replace('(r["created_at"], r["id"]) > marker', 'r["created_at"] > marker[0]').replace('if len(rows) > len(page) else None', 'if page else None'),
        "workshop/service.py": cursor_service.replace('return {"error": "invalid_cursor"}', 'marker = None')},
    "reference": {"workshop/repository.py": cursor_repo, "workshop/pagination.py": cursor_paging, "workshop/service.py": cursor_service},
    "partial": {"workshop/service.py": cursor_service.replace('return {"error": "invalid_cursor"}', 'marker = None')},
    "public": cursor_public, "hidden": cursor_hidden, "cursor_output": True})


COMPARATORS = code('''
    def equivalent(actual, expected):
        if type(expected) is dict:
            return type(actual) is dict and actual.keys() == expected.keys() and all(equivalent(actual[k], v) for k, v in expected.items())
        if type(expected) is list:
            return type(actual) is list and len(actual) == len(expected) and all(equivalent(a, e) for a, e in zip(actual, expected))
        if type(expected) is bool:
            return type(actual) is bool and actual == expected
        if type(expected) in (int, float):
            return type(actual) in (int, float) and actual == expected
        return type(actual) is type(expected) and actual == expected

    def normalize_cursor(value):
        if type(value) is not dict or value.get("next_cursor") is None:
            return value
        try:
            token = value["next_cursor"]
            assert type(token) is str
            payload = json.loads(base64.b64decode(token + "=" * (-len(token) % 4), altchars=b"-_", validate=True))
            assert type(payload) is dict and set(payload) == {"v", "ts", "id"}
            assert type(payload["v"]) is int and payload["v"] == 1
            assert type(payload["ts"]) is int and type(payload["id"]) is int and payload["id"] >= 1
            return {**value, "next_cursor": payload}
        except Exception as exc:
            raise AssertionError("Invalid output cursor") from exc
''')


def check_script(cases, cursor=False, traverse=False):
    traversal = code('''
        datasets = {}
        for item in cases:
            records = item["request"]["records"]
            datasets[json.dumps(records, sort_keys=True)] = records
        for records in datasets.values():
            token, collected, seen = None, [], set()
            for step in range(len(records) + 2):
                request = {"records": deepcopy(records), "limit": 2, "cursor": token}
                before = json.dumps(request, sort_keys=True)
                actual = submission.run(request)
                assert json.dumps(request, sort_keys=True) == before, "Traversal mutated input"
                assert type(actual) is dict and set(actual) == {"items", "next_cursor"}
                assert type(actual["items"]) is list and len(actual["items"]) <= 2
                collected.extend(actual["items"])
                token = actual["next_cursor"]
                if token is None:
                    break
                assert actual["items"], "Empty page returned a cursor"
                normalized = normalize_cursor(actual)["next_cursor"]
                marker = normalized["ts"], normalized["id"]
                assert marker not in seen, "Cursor did not progress"
                assert marker == (actual["items"][-1]["created_at"], actual["items"][-1]["id"])
                seen.add(marker)
            else:
                raise AssertionError("Traversal did not terminate")
            assert equivalent(collected, sorted(records, key=lambda r: (r["created_at"], r["id"]))), "Traversal lost or duplicated records"
        print(f"Verified complete traversal of {len(datasets)} datasets")
    ''') if traverse else ""
    return ("from copy import deepcopy\nimport base64\nimport json\nimport os\nfrom pathlib import Path\n"
            "from check_client import load_submission\n\n" + COMPARATORS +
            "\ncases = json.loads(" + repr(json.dumps(cases, ensure_ascii=True)) + ")\n" +
            "submission = load_submission(Path(os.environ['LAB_WORKSPACE']) / 'app.py')\n" +
            "for index, item in enumerate(cases, 1):\n"
            "    request = deepcopy(item['request'])\n"
            "    before = json.dumps(request, sort_keys=True)\n"
            "    actual = submission.run(request)\n"
            "    assert json.dumps(request, sort_keys=True) == before, f'Input mutated at case {index}'\n"
            + ("    actual, expected = normalize_cursor(actual), normalize_cursor(item['expected'])\n" if cursor else "    expected = item['expected']\n") +
            "    assert equivalent(actual, expected), f'Wrong result at case {index}: expected {expected!r}, got {actual!r}'\n"
            "print(f'Executed {len(cases)} repository cases successfully')\n" + traversal)


def smoke_script(cases, cursor=False):
    return ("import base64\nimport json\nimport unittest\nfrom copy import deepcopy\nfrom app import run\n\n" + COMPARATORS +
            "\nCASES = json.loads(" + repr(json.dumps(cases, ensure_ascii=True)) + ")\n" +
            "class SmokeTests(unittest.TestCase):\n"
            "    def test_public_contract(self):\n"
            "        for index, item in enumerate(CASES, 1):\n"
            "            with self.subTest(case=index):\n"
            "                request = deepcopy(item['request'])\n"
            "                before = json.dumps(request, sort_keys=True)\n"
            "                actual = run(request)\n"
            "                self.assertEqual(json.dumps(request, sort_keys=True), before)\n" +
            ("                actual, expected = normalize_cursor(actual), normalize_cursor(item['expected'])\n" if cursor else "                expected = item['expected']\n") +
            "                self.assertTrue(equivalent(actual, expected), (actual, expected))\n"
            "if __name__ == '__main__':\n    unittest.main()\n")


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build():
    if SUITE.exists():
        raise SystemExit("Suite already exists; build a new version instead of overwriting frozen tasks")
    manifest = {"schema_version": 1, "id": "repo-workflows-v1", "origin": "original synthetic mini repositories",
                "created_on": "2026-10-31", "split": "development", "tasks": []}
    for spec in TASKS:
        folder = SUITE / "tasks" / spec["id"]
        files = {"app.py": code('''
            """Stable JSON-callable entry point for local and isolated execution."""
            from pathlib import Path
            import sys
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from workshop.service import run
        '''), "workshop/__init__.py": "", **spec["files"]}
        files["tests/test_smoke.py"] = smoke_script(spec["public"], spec.get("cursor_output", False))
        files["README.md"] = ("# " + spec["title"] + "\n\n" + spec["description"] + "\n\n" +
            "\n".join("- " + line for line in spec["acceptance"]) +
            "\n\n入口是 app.run(request)。公开样例在 tests/test_smoke.py，可使用实验工具 run_checks 运行公开验收。\n"
            "本地开发也可在仓库根目录执行 python -m unittest discover -s tests。无外部依赖、网络或真实等待。\n")
        for name, text in files.items():
            write(folder / "source" / name, text)
        task = {"schema_version": 1, "id": spec["id"], "description": spec["description"] + " 阅读 README.md 与现有代码，使用 app.run(request) 保持外部接口。",
                "acceptance": spec["acceptance"], "source_dir": "source", "editable_files": list(spec["reference"]),
                "public_check": "public_check.py", "final_check": "final_check.py"}
        write(folder / "task.json", json.dumps(task, ensure_ascii=False, indent=2) + "\n")
        write(folder / "public_check.py", check_script(spec["public"], spec.get("cursor_output", False)))
        write(folder / "final_check.py", check_script(spec["public"] + spec["hidden"], spec.get("cursor_output", False), spec.get("cursor_output", False)))
        for name, text in spec["reference"].items():
            write(folder / "operator/reference" / name, text)
        variants = {"partial-fix": spec["partial"], **spec.get("extra_mutants", {})}
        for name, patch in variants.items():
            write(folder / "operator/mutants" / (name + ".json"), json.dumps(patch, indent=2) + "\n")
        manifest["tasks"].append({"id": spec["id"], "title": spec["title"], "category": spec["category"],
            "manifest": "tasks/" + spec["id"] + "/task.json", "source_files": len(files),
            "editable_files": len(spec["reference"]), "public_cases": len(spec["public"]),
            "final_cases": len(spec["public"]) + len(spec["hidden"]),
            "final_properties": ["complete cursor traversal without lost or duplicated records"] if spec.get("cursor_output") else [],
            "difficulty": "unmeasured"})
    write(SUITE / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print("Built", len(TASKS), "repository tasks in", SUITE)


if __name__ == "__main__":
    build()
