# Structure Router middle-difficulty candidates

Two tasks based on fixes in real Python libraries. Each task bundles the Python package at the parent of the upstream merge commit and retains its upstream licenses. The source and reference commits and archive hashes are in [manifest.json](manifest.json). The middle-difficulty label is provisional until the fixed architectures are compared.

| Task | Behavior | Public / final scenarios |
| --- | --- | ---: |
| [TOMLKit round-trip](tasks/python-tomlkit-dotted-table-roundtrip/task.json) | Root fields stay at the root when a dotted key gains a child table. Inline dotted keys keep their existing layout. | 2 / 6 |
| [Packaging dependency-group errors](tasks/python-packaging-dependency-group-errors/task.json) | Invalid requirement strings join other group errors. Valid expansion, order, and cycle detection still work. | 2 / 9 |

The library code and check adapters run on the existing Windows/Python 3.12 environment. Agents see only the task contract and `source/`, including the public scenarios. The operator-owned final checks, upstream reference code and partial fixes live outside that directory.

The [Luna solo configuration](../../configs/workflow-structure-router-middle-luna-solo.json) combines these two tasks with the existing TinyDB snapshot task. It uses the Plan20 four-turn workflow and Luna profile, with a $2 batch limit.

The offline audit tests the starter, upstream reference, a partial fix that passes the public checks, and premature process exit:

```powershell
.\.venv\Scripts\python.exe scripts/audit_repo_tasks.py --suite benchmarks/router-middle-v1 --output artifacts/router-middle-audit
.\run-lab.cmd validate --experiment configs/workflow-structure-router-middle-luna-solo.json
```
