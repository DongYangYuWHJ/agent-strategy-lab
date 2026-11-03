# SWE-bench Pro V2 engineering-task selection

Eight real-repository development tasks, pinned to upstream commit
`66f92766bba642462d4bbe5479e83f91f9211862`.

See [task scope and integration status](../../docs/larger-repo-tasks.md).
`selection.json` is curator metadata, not a runnable lab configuration and not
an agent prompt. Reference patch statistics must remain outside agent inputs.

Prepare the original task materials with:

```powershell
.\.venv\Scripts\python.exe scripts/prepare_upstream_repo_tasks.py
```

Downloaded solutions and hidden tests live under the Git-ignored
`artifacts/swebench-pro-v2-intake/operator/` directory. Never expose that
directory to solving agents. Complete repository environments require the
upstream container images; no model calls or upstream scripts are executed by
the preparation command.
