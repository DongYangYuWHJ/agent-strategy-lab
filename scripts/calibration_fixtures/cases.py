"""Operator-authored expectations, independent of the reference implementations."""
from copy import deepcopy


def item(request, expected, group="feature"):
    return {"request": request, "expected": expected, "group": group}


def doc(i, **data):
    return {"id": i, "data": data}


def insert(value, table="_default"):
    return {"op": "insert", "data": {"n": value}, "table": table}


def tx(steps, catch=False):
    return {"op": "transaction", "steps": steps, "catch": catch}


def dbcase(steps, results, state, group="feature", backend="memory"):
    return item({"steps": steps, "backend": backend}, {"results": results, "state": state}, group)


def transactions():
    public = [
        dbcase([tx([insert(1), insert(2, "other")]), {"op": "writes"}],
               [[1, 1], 1], {"_default": [doc(1, n=1)], "other": [doc(1, n=2)]}, "commit"),
        dbcase([insert(1), tx([insert(2), {"op": "fail"}], True), {"op": "all"}],
               [1, {"error": "RuntimeError"}, [doc(1, n=1)]], {"_default": [doc(1, n=1)]}, "rollback"),
        dbcase([insert(1), {"op": "update", "ids": [1], "data": {"n": 3}}, {"op": "all"}],
               [1, [1], [doc(1, n=3)]], {"_default": [doc(1, n=3)]}, "regression"),
    ]
    extra = [
        dbcase([insert(1), tx([insert(2), {"op": "fail"}], True), insert(3)],
               [1, {"error": "RuntimeError"}, 2], {"_default": [doc(1, n=1), doc(2, n=3)]}, "rollback-id"),
        dbcase([tx([insert(1), tx([insert(2), {"op": "fail"}], True), insert(3)]), {"op": "writes"}],
               [[1, {"error": "RuntimeError"}, 2], 1], {"_default": [doc(1, n=1), doc(2, n=3)]}, "savepoint"),
        dbcase([tx([insert(1), tx([insert(2, "other")]), {"op": "fail"}], True), {"op": "writes"}],
               [{"error": "RuntimeError"}, 0], {}, "outer-rollback"),
        dbcase([insert(1), {"op": "search", "field": "n", "value": 1},
                tx([{"op": "update", "ids": [1], "data": {"n": 2}},
                    {"op": "search", "field": "n", "value": 2}, {"op": "fail"}], True),
                {"op": "search", "field": "n", "value": 1}],
               [1, [doc(1, n=1)], {"error": "RuntimeError"}, [doc(1, n=1)]],
               {"_default": [doc(1, n=1)]}, "cache-rollback"),
        dbcase([insert(1), tx([{"op": "backing"}, insert(2), {"op": "backing"}])],
               [1, [{"_default": {"1": {"n": 1}}}, 2, {"_default": {"1": {"n": 1}}}]],
               {"_default": [doc(1, n=1), doc(2, n=2)]}, "isolation"),
        dbcase([tx([]), {"op": "writes"}, insert(4)], [[], 1, 1],
               {"_default": [doc(1, n=4)]}, "empty"),
        dbcase([insert(1), tx([{"op": "remove", "ids": [1]}, insert(9, "other")]),
                {"op": "search", "field": "n", "value": 1}],
               [1, [[1], 1], []], {"_default": [], "other": [doc(1, n=9)]}, "multi-table"),
    ]
    final = list(public)
    for backend in ("memory", "json", "cached"):
        for value in extra:
            copied = deepcopy(value)
            copied["request"]["backend"] = backend
            final.append(copied)
        if backend != "memory":
            final.append(dbcase([tx([insert(8), insert(9, "other")]), {"op": "reopen"}],
                                [[1, 1], True], {"_default": [doc(1, n=8)], "other": [doc(1, n=9)]},
                                "persistence", backend))
    return public, final


def snapshot(rows=None):
    return {"version": 1, "tables": {"_default": [doc(5, n=5)]} if rows is None else rows}


def restore(value, **kw):
    return {"op": "restore", "snapshot": value, **kw}


def snapshots():
    public = [
        dbcase([insert(1), {"op": "export"}], [1, snapshot({"_default": [doc(1, n=1)]})],
               {"_default": [doc(1, n=1)]}, "export"),
        dbcase([insert(1), restore(snapshot()), {"op": "all"}],
               [1, {"tables": 1, "documents": 1}, [doc(5, n=5)]], {"_default": [doc(5, n=5)]}, "replace"),
        dbcase([insert(1), restore(snapshot(), dry_run=True)],
               [1, {"tables": 1, "documents": 1}], {"_default": [doc(1, n=1)]}, "dry-run"),
        dbcase([insert(2), {"op": "remove", "ids": [1]}, insert(3)],
               [1, [1], 2], {"_default": [doc(2, n=3)]}, "regression"),
    ]
    extras = [
        dbcase([insert(1), restore(snapshot({"_default": [doc(1, n=9)]}), mode="reject", catch=True)],
               [1, {"error": "ValueError"}], {"_default": [doc(1, n=1)]}, "reject-conflict"),
        dbcase([insert(1), insert(2, "old"), restore(snapshot(), mode="merge"), insert(6)],
               [1, 1, {"tables": 2, "documents": 3}, 6],
               {"_default": [doc(1, n=1), doc(5, n=5), doc(6, n=6)], "old": [doc(1, n=2)]}, "merge-id"),
        dbcase([insert(1), {"op": "search", "field": "n", "value": 1}, restore(snapshot()),
                {"op": "search", "field": "n", "value": 1}, insert(7)],
               [1, [doc(1, n=1)], {"tables": 1, "documents": 1}, [], 6],
               {"_default": [doc(5, n=5), doc(6, n=7)]}, "handles-cache-id"),
        dbcase([restore(snapshot(), mutate_input=True), {"op": "export"}, {"op": "mutate_export"}],
               [{"tables": 1, "documents": 1}, snapshot(), True], {"_default": [doc(5, n=5)]}, "copy-isolation"),
        dbcase([insert(1), restore(snapshot({}), mode="replace")], [1, {"tables": 0, "documents": 0}], {}, "empty-replace"),
        dbcase([insert(1), restore(snapshot({"other": [doc(2, n=2)]}), mode="reject")],
               [1, {"tables": 2, "documents": 2}], {"_default": [doc(1, n=1)], "other": [doc(2, n=2)]}, "reject-disjoint"),
        dbcase([insert(1), restore(snapshot({"_default": [doc(1, n=7)]}), mode="merge")],
               [1, {"tables": 1, "documents": 1}], {"_default": [doc(1, n=7)]}, "merge-overwrite"),
    ]
    invalid = [None, {}, {"version": True, "tables": {}}, {"version": 2, "tables": {}},
               snapshot({"": []}), snapshot({"x": {}}), snapshot({"x": [doc(0)]}),
               snapshot({"x": [doc(True)]}), snapshot({"x": [doc(2), doc(2)]}),
               snapshot({"x": [{"id": 1, "data": []}]}),
               snapshot({"first": [doc(3)], "last": [doc(-1)]})]
    for value in invalid:
        extras.append(dbcase([insert(1), restore(value, catch=True)], [1, {"error": "ValueError"}],
                             {"_default": [doc(1, n=1)]}, "validation-atomicity"))
    final = list(public)
    for backend in ("memory", "json", "cached"):
        for value in extras:
            copied = deepcopy(value)
            copied["request"]["backend"] = backend
            final.append(copied)
        final.append(dbcase([insert(1), restore(snapshot(), dry_run=True), insert(2)],
                            [1, {"tables": 1, "documents": 1}, 2],
                            {"_default": [doc(1, n=1), doc(2, n=2)]}, "dry-run-id", backend))
        if backend != "memory":
            final.append(dbcase([restore(snapshot()), {"op": "reopen"}, insert(6)],
                                [{"tables": 1, "documents": 1}, True, 6],
                                {"_default": [doc(5, n=5), doc(6, n=6)]}, "persistence", backend))
    return public, final


def claims():
    base = {"mode": "claims", "payload": {"user": 7}}
    public = [item(base, {"value": {"user": 7}}, "claims"),
              item({**base, "check_at": 121}, {"error": "SignatureExpired"}, "expiry"),
              item({"mode": "regression", "payload": [1, None]}, {"value": [1, None]}, "regression")]
    variants = [({}, {"value": {"user": 7}}, "claims"),
                ({"check_at": 120}, {"error": "SignatureExpired"}, "expiry-boundary"),
                ({"check_at": 119}, {"value": {"user": 7}}, "expiry-boundary"),
                ({"check_at": 120, "leeway": 1}, {"value": {"user": 7}}, "leeway"),
                ({"check_at": 121, "leeway": 1}, {"error": "SignatureExpired"}, "leeway"),
                ({"check_at": 99}, {"error": "SignatureExpired"}, "future-issue"),
                ({"not_before": 115, "check_at": 114}, {"error": "SignatureExpired"}, "activation"),
                ({"not_before": 115, "check_at": 114, "leeway": 1}, {"value": {"user": 7}}, "activation"),
                ({"verify_audience": "web"}, {"error": "BadSignature"}, "audience"),
                ({"tamper": True}, {"error": "BadSignature"}, "signature"),
                ({"verifier": {"salt": "different"}}, {"error": "BadSignature"}, "salt"),
                ({"verifier": {"keys": ["wrong"]}}, {"error": "BadSignature"}, "key"),
                ({"current": {"keys": ["old"]}, "verifier": {"keys": ["old", "new"]}},
                 {"value": {"user": 7}}, "rotation-regression"),
                ({"leeway": -1}, {"error": "ValueError"}, "validation"),
                ({"leeway": True}, {"error": "ValueError"}, "validation")]
    raw = {"v": 1, "aud": "api", "iat": 100, "nbf": 100, "exp": 120, "payload": {"user": 7}}
    for malformed in [None, {}, {**raw, "v": True}, {**raw, "exp": True},
                      {**raw, "iat": 121}, {**raw, "nbf": 120}, {**raw, "extra": 1}]:
        variants.append(({"raw": malformed}, {"error": "BadSignature"}, "signed-malformed"))
    final = list(public)
    for kind in ("plain", "url", "timed", "url_timed"):
        for kw, expected, group in variants:
            final.append(item({**base, **kw, "kind": kind}, expected, group))
        for payload in [None, [False, {"nested": "value"}], "x" * 1000]:
            final.append(item({**base, "kind": kind, "payload": payload}, {"value": payload}, "payload-regression"))
    for arguments in [{"audience": "", "now": 100, "ttl": 5}, {"audience": "api", "now": True, "ttl": 5},
                      {"audience": "api", "now": 100, "ttl": 0}, {"audience": "api", "now": 100, "ttl": True},
                      {"audience": "api", "now": 100, "ttl": 20, "not_before": 120}]:
        final.append(item({"mode": "invalid_issue", "arguments": arguments}, {"error": "ValueError"}, "issue-validation"))
    return public, final


def migrations():
    origin = {"keys": ["old"], "salt": "old-salt", "digest": "sha1"}
    base = {"mode": "migration", "origin": origin, "legacy": [origin], "payload": {"user": 7}}
    plain = {"value": {"user": 7}, "current_value": {"user": 7}, "source": 1, "old_accepts": False}
    public = [item(base, plain, "migration"),
              item({**base, "kind": "plain"}, plain, "serialization"),
              item({"mode": "regression", "payload": {"a": 1}}, {"value": {"a": 1}}, "regression")]
    final = list(public)
    for kind in ("plain", "url", "timed", "url_timed"):
        timed = kind in ("timed", "url_timed")
        expected = {**plain, **({"signed_at": 1700000000, "later": "SignatureExpired"} if timed else {})}
        for payload in [{"user": 7}, None, "compressed-" * 100, [1, False, {"n": 3}]]:
            final.append(item({**base, "kind": kind, "payload": payload},
                              {**expected, "value": payload, "current_value": payload}, "migration-payload"))
        for kw in [{"legacy": []}, {"tamper": True}, {"legacy": [{**origin, "salt": "bad"}]}]:
            final.append(item({**base, "kind": kind, **kw}, {"error": "BadSignature"}, "reject-untrusted"))
        final.append(item({**base, "kind": kind, "legacy": [{"keys": ["wrong"]}, origin]},
                          {**expected, "source": 2}, "candidate-order"))
        final.append(item({**base, "kind": kind, "origin": {}, "legacy": []},
                          {**expected, "source": 0, "old_accepts": True}, "current-token"))
        final.append(item({**base, "kind": kind, "legacy": [{"kind": "url" if timed else "url_timed"}]},
                          {"error": "ValueError"}, "type-validation"))
        other_kind = {"plain": "url", "url": "plain", "timed": "url_timed", "url_timed": "timed"}[kind]
        final.append(item({**base, "kind": kind, "origin": {"kind": other_kind},
                           "legacy": [{"kind": other_kind}]},
                          expected, "cross-format"))
        if timed:
            for checked, maximum, expected_result in [(1700000020, 20, expected),
                                                       (1700000021, 20, {"error": "SignatureExpired"}),
                                                       (1699999999, 20, {"error": "SignatureExpired"})]:
                final.append(item({**base, "kind": kind, "checked_at": checked, "max_age": maximum},
                                  expected_result, "age-preservation"))
            final.append(item({**base, "kind": kind, "current": {"keys": ["old", "new"]},
                               "origin": {"keys": ["old"]}, "legacy": []},
                              {**expected, "source": 0}, "rotation"))
        else:
            final.append(item({**base, "kind": kind, "max_age": 20}, {"error": "ValueError"}, "age-validation"))
    return public, final


def put(key, value):
    return {"op": "put", "key": key, "value": value}


def cachecase(steps, results, group="feature", **kw):
    return item({"steps": steps, **kw}, {"results": results}, group)


def state(items, maximum, size=None):
    return {"items": items, "maxsize": maximum, "currsize": len(items) if size is None else size}


def resizes():
    public = [cachecase([put("a", 1), put("b", 2), put("c", 3), {"op": "resize", "size": 2}, {"op": "state"}],
                        [None, None, None, [["a", 1]], state([["b", 2], ["c", 3]], 2)], "shrink"),
              cachecase([put("a", 1), {"op": "resize", "size": 5}, {"op": "get", "key": "a"}],
                        [None, [], 1], "grow"),
              cachecase([put("a", 1), {"op": "memo", "key": "b", "value": 2}],
                        [None, [2, 2, 1]], "regression")]
    final = list(public)
    for kind in ("Cache", "FIFOCache", "LRUCache", "TTLCache"):
        final.append(cachecase([put("a", 1), put("b", 2), put("c", 3), {"op": "resize", "size": 1}, {"op": "state"}],
                               [None, None, None, [["a", 1], ["b", 2]], state([["c", 3]], 1)], "multi-evict", kind=kind))
        for invalid in [0, -1, True, 2.5, "2", None]:
            final.append(cachecase([put("a", 1), {"op": "resize", "size": invalid}, {"op": "state"}],
                                   [None, {"error": "ValueError"}, state([["a", 1]], 3)], "invalid-unchanged", kind=kind))
        final.append(cachecase([put("a", "xxx"), put("b", "yy"), {"op": "resize", "size": 2}, {"op": "state"},
                                put("z", "long"), {"op": "state"}],
                               [None, None, [["a", "xxx"]], state([["b", "yy"]], 2, 2),
                                {"error": "ValueError"}, state([["b", "yy"]], 2, 2)],
                               "weighted", kind=kind, maxsize=6, weighted=True))
    for kind, victim in [("LRUCache", "b"), ("FIFOCache", "a"), ("TTLCache", "b")]:
        survivor = "a" if victim == "b" else "b"
        final.append(cachecase([put("a", 1), put("b", 2), {"op": "get", "key": "a"},
                                {"op": "resize", "size": 1}, {"op": "popitem"}],
                               [None, None, 1, [[victim, 2 if victim == "b" else 1]],
                                [survivor, 1 if survivor == "a" else 2]], "policy-order", kind=kind))
    final.append(cachecase([put("a", 1), {"op": "advance", "seconds": 10},
                            {"op": "resize", "size": 1}, {"op": "state"}, put("b", 2), {"op": "get", "key": "b"}],
                           [None, 10, [], state([], 1), None, 2], "expiry", kind="TTLCache"))
    final.append(cachecase([put("a", 1), put("b", 2), {"op": "get", "key": "a"},
                            {"op": "resize", "size": 1}, {"op": "state"}],
                           [None, None, 1, [["b", 2]], state([["a", 1]], 1)], "frequency", kind="LFUCache"))
    return public, final


def atomics():
    public = [cachecase([{"op": "atomic", "pairs": [["a", 1], ["b", 2]]}, {"op": "state"}],
                        [2, state([["a", 1], ["b", 2]], 3)], "commit"),
              cachecase([put("a", 1), {"op": "atomic", "pairs": []}, {"op": "get", "key": "a"}],
                        [None, 0, 1], "empty"),
              cachecase([put("a", 1), {"op": "memo", "key": "b", "value": 2}],
                        [None, [2, 2, 1]], "regression")]
    final = list(public)
    for kind in ("Cache", "FIFOCache", "LRUCache", "LFUCache", "TTLCache"):
        final.append(cachecase([put("a", 1), {"op": "atomic", "pairs": [["b", 2]], "fail_iterator": True}, {"op": "state"}],
                               [None, {"error": "RuntimeError"}, state([["a", 1]], 3)], "iterator-rollback", kind=kind))
        final.append(cachecase([put("a", "xx"), {"op": "atomic", "pairs": [["b", "yy"], ["c", "oversize"]]},
                                {"op": "state"}, {"op": "popitem"}],
                               [None, {"error": "ValueError"}, state([["a", "xx"]], 3, 2), ["a", "xx"]],
                               "size-rollback", kind=kind, weighted=True))
        final.append(cachecase([put("a", "xx"), {"op": "atomic", "pairs": [["b", "x"], ["c", 3]]},
                                {"op": "state"}],
                               [None, {"error": "TypeError"}, state([["a", "xx"]], 3, 2)],
                               "sizing-error-rollback", kind=kind, weighted=True))
        final.append(cachecase([put("a", 1), {"op": "atomic", "pairs": [["b", 2], ["x"]]}, {"op": "state"}],
                               [None, {"error": "ValueError"}, state([["a", 1]], 3)], "malformed-rollback", kind=kind))
        final.append(cachecase([{"op": "atomic", "pairs": [["a", 1], ["a", 2], ["b", 3]]}, {"op": "state"}],
                               [3, state([["a", 2], ["b", 3]], 3)], "duplicate-key", kind=kind))
    for kind in ("LRUCache", "FIFOCache", "TTLCache"):
        final.append(cachecase([put("a", 1), put("b", 2), {"op": "get", "key": "a"},
                                {"op": "atomic", "pairs": [["c", 3]], "fail_iterator": True}, {"op": "popitem"}],
                               [None, None, 1, {"error": "RuntimeError"}, ["a", 1] if kind == "FIFOCache" else ["b", 2]],
                               "order-rollback", kind=kind, maxsize=2))
    final.append(cachecase([put("a", 1), {"op": "advance", "seconds": 5},
                            {"op": "atomic", "pairs": [["b", 2]]}, {"op": "advance", "seconds": 5},
                            {"op": "state"}, {"op": "advance", "seconds": 5}, {"op": "state"}],
                           [None, 5, 1, 10, state([["b", 2]], 3), 15, state([], 3)], "ttl-preservation", kind="TTLCache"))
    final.append(cachecase([{"op": "atomic", "pairs": [["a", 1], ["b", 2], ["c", 3], ["d", 4]]},
                            {"op": "state"}, {"op": "memo", "key": "d", "value": 9}],
                           [4, state([["b", 2], ["c", 3], ["d", 4]], 3), [4, 4, 0]], "eviction-decorator"))
    final.append(cachecase([put("a", 1), put("b", 2), {"op": "get", "key": "a"},
                            {"op": "atomic", "pairs": [["c", 3]], "fail_iterator": True}, {"op": "popitem"}],
                           [None, None, 1, {"error": "RuntimeError"}, ["b", 2]], "frequency-rollback",
                           kind="LFUCache", maxsize=2))
    return public, final


def database_integration():
    p1, f1 = transactions()
    p2, f2 = snapshots()
    public = p1 + p2
    final = f1 + f2
    for backend in ("memory", "json", "cached"):
        final.append(dbcase([insert(1), tx([restore(snapshot()), {"op": "export"}, {"op": "fail"}], True),
                             insert(2), {"op": "all"}],
                            [1, {"error": "RuntimeError"}, 2, [doc(1, n=1), doc(2, n=2)]],
                            {"_default": [doc(1, n=1), doc(2, n=2)]}, "restore-rollback", backend))
        final.append(dbcase([tx([insert(1), {"op": "export"}, restore(snapshot(), dry_run=True),
                                 insert(2), {"op": "writes"}]), {"op": "writes"}],
                            [[1, snapshot({"_default": [doc(1, n=1)]}), {"tables": 1, "documents": 1}, 2, 0], 1],
                            {"_default": [doc(1, n=1), doc(2, n=2)]}, "snapshot-dry-run-transaction", backend))
        final.append(dbcase([tx([restore(snapshot()), tx([restore(snapshot({})), {"op": "fail"}], True), insert(6)]),
                             {"op": "writes"}],
                            [[{"tables": 1, "documents": 1}, {"error": "RuntimeError"}, 6], 1],
                            {"_default": [doc(5, n=5), doc(6, n=6)]}, "restore-savepoint", backend))
    return public, final


def signing_integration():
    p1, f1 = claims()
    p2, f2 = migrations()
    public = p1 + p2
    final = f1 + f2
    origin = {"keys": ["old"], "salt": "previous", "digest": "sha1"}
    for kind in ("plain", "url", "timed", "url_timed"):
        for check_at, audience, expected in [(119, "api", {"value": [1, {"x": 3}]}),
                                              (120, "api", {"error": "SignatureExpired"}),
                                              (110, "other", {"error": "BadSignature"})]:
            result = {**expected, "source": 1}
            if kind in ("timed", "url_timed"):
                result["signed_at"] = 1700000000
            final.append(item({"mode": "claims_migration", "origin": origin, "kind": kind,
                               "payload": [1, {"x": 3}], "check_at": check_at, "verify_audience": audience},
                              result, "claims-migration-preservation"))
    return public, final


def cache_integration():
    p1, f1 = resizes()
    p2, f2 = atomics()
    public = p1 + p2
    final = f1 + f2
    for kind in ("Cache", "FIFOCache", "LRUCache", "TTLCache"):
        final.append(cachecase([put("a", 1), put("b", 2), {"op": "resize", "size": 1},
                                {"op": "atomic", "pairs": [["c", 3]], "fail_iterator": True}, {"op": "state"},
                                {"op": "atomic", "pairs": [["d", 4]]}, {"op": "state"}],
                               [None, None, [["a", 1]], {"error": "RuntimeError"}, state([["b", 2]], 1),
                                1, state([["d", 4]], 1)], "resize-atomic-rollback", kind=kind))
    final.append(cachecase([put("a", "xxx"), {"op": "resize", "size": 2},
                            {"op": "atomic", "pairs": [["b", "yy"], ["c", "xxx"]]}, {"op": "state"},
                            {"op": "atomic", "pairs": [["b", "yy"]]}, {"op": "state"}],
                           [None, [["a", "xxx"]], {"error": "ValueError"}, state([], 2, 0),
                            1, state([["b", "yy"]], 2, 2)], "new-capacity-atomic", weighted=True, maxsize=5))
    return public, final
