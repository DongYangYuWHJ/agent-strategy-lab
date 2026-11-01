# 仓库开发任务集 v1

为补充算法题的任务类型，新增六个原创、自包含 Python 小仓库。每个仓库包含业务模块、固定 `app.run(request)` 入口、README 和公开测试，无第三方依赖、真实网络或等待。这些任务来自手工构造，任务规模仍小；是否比已有题更能区分模型，需要线上实验确认。

| 类别 | 任务 | 要求与回归重点 | 可编辑文件数 |
|---|---|---|---:|
| 局部修复 | [分页 API 边界](../benchmarks/repo-workflows-v1/tasks/repo-page-boundaries/task.json) | 页末、空集合、参数校验、返回元数据 | 1 |
| 局部修复 | [HTTP 重试策略](../benchmarks/repo-workflows-v1/tasks/repo-retry-policy/task.json) | 永久错误、重试次数、退避及 Retry-After=0 | 1 |
| 跨文件修改 | [超时设置贯通](../benchmarks/repo-workflows-v1/tasks/repo-timeout-wiring/task.json) | CLI／环境／配置优先级、零值、传输层单位转换 | 4 |
| 跨文件修改 | [笔记软删除与恢复](../benchmarks/repo-workflows-v1/tasks/repo-note-soft-delete/task.json) | 列表、详情、恢复、更新及创建冲突保持一致 | 3 |
| 问题定位 | [缓存隔离与污染](../benchmarks/repo-workflows-v1/tasks/repo-cache-isolation/task.json) | 租户／权限隔离、对象复制、局部失效、缓存命中 | 2 |
| 问题定位 | [游标分页丢记录](../benchmarks/repo-workflows-v1/tasks/repo-cursor-pagination/task.json) | 相同时间戳排序、连续翻页、非法游标、末页语义 | 3 |

每个任务有 6–9 个源码／说明／公开测试文件，明确限定可编辑范围。类别不等于难度等级；难度字段为 `unmeasured`。本批全部属于开发集，未建立仓库任务的保留评估集。原 LiveCodeBench 任务及保留集保持原样。

## 输入、输出与验收

- 输入是开发需求、已有代码、公开接口约定和可编辑文件列表。继续使用 [原四轮用户提示](../configs/workflows/daily-review.json)，不增加 Router 或 Planner 角色。
- 输出是代码修改及模型对用户的回复。独立验收检查入口行为、跨模块接线、原有功能回归和输入不被修改；不要求模型采用参考解法的代码结构或算法。
- 每题三组公开场景，可通过 `run_checks` 执行，源码中的 `tests/test_smoke.py` 也可阅读。最终验收包含公开及额外回归场景，共 139 组固定场景，游标任务另有完整翻页性质检查。隐藏结果不用于追加模型提示。
- 最终验收覆盖声明的场景，不等于证明所有实现都无缺陷，也不评价开放式代码风格或真实生产维护质量。

参考修复和负对照保存在各题 `operator/`，公开／最终验收器在题目录下，均位于 `source/` 外。模型文件工具只能访问 `source/` 白名单，不会收到这些操作者文件。验收使用既有独立子进程和完成回执机制，提前退出或打印“通过”不能代替结果。

## 离线审计与生成

[构建脚本](../scripts/build_repo_tasks.py) 固定生成内容、随机种子和原始任务元数据；拒绝覆盖已有任务集。开发时重新生成到隔离目录，87 个生成文件逐字节一致。

[审计脚本](../scripts/audit_repo_tasks.py) 使用正式验收运行器，检查 25 组对照：原始缺陷失败、参考修复通过、只过公开样例的部分修复在最终验收失败、提前退出失败；缓存任务额外拒绝“关闭缓存”的实现。每组均执行公开与最终验收，六个参考仓库的普通 unittest 公开测试也已验证通过。

证据：[审计结果](../artifacts/repo-workflows-audit-20261031-02/audit.json)。原始任务和验收器审计前后指纹不变；本地证据在被 Git 忽略的 artifacts 中。重新审计使用新目录：

```powershell
.\.venv\Scripts\python.exe scripts/audit_repo_tasks.py --output artifacts/repo-task-audit-local-01
```

## 后续模型比较

[配置入口](../configs/workflow-repo-single.json) 配置 DeepSeek low 单体与 Sol medium 单体，各六题、一次，共十二例；每例 $0.50、批次 $6.00。两者使用现有部署参数：DeepSeek 不设本地输出／累计 Token 门禁，Sol 保留输出 16384 及累计 200000；因此比较是当前两套模型配置的工作表现，不是相等推理预算的能力测量。时间、调用次数、文件工具与验收一致。

2026-10-31 已完成首轮十二项记录：Sol 正式 6/6；DeepSeek 正式 4/6，另两例为传输中断和本地公开验收计时异常（后者隐藏验收通过）。未重跑失败例，原批次暂停后仅以独立预算继续未开始的任务。四个正常完成的成对任务中，DeepSeek 合计 $0.045583008，Sol $0.1854090；不能用正式通过数直接判断模型能力，完整 DeepSeek 费用仍有一次未知请求。[合并报告及范围说明](../artifacts/repo-single-live-20261031-01/comparison.md)。

2026-11-01 用 [DeepSeek／GPT-6 Luna 配置](../configs/workflow-repo-deepseek-luna.json) 另做十二项记录，各一次：Luna 正式 6/6，DeepSeek 正式 5/6，另一次游标题请求未完成、用量未知。五个干净配对中 Luna $0.023318810、DeepSeek $0.064420680，Luna 低约 63.8%，但配对累计耗时较长。没有功能验收失败，异常请求未重跑；详细记录、分段预算及比较边界见 [本轮报告](../artifacts/repo-deepseek-luna-live-20261101-01/comparison.md)。两轮结果独立保留。

任务通过 `task_globs` 自动发现 `benchmarks/repo-workflows-v1/tasks/*/task.json`。新增同类任务后无需手写 Python 数组；同时应维护 suite 的 manifest、控制样本和审计。

只检查配置和预览任务，不调用模型：

```powershell
.\run-lab.cmd validate --experiment configs/workflow-repo-single.json --catalog configs/models-workflow-comparison.json
.\run-lab.cmd list-tasks --experiment configs/workflow-repo-single.json --catalog configs/models-workflow-comparison.json
```

另开新批次进行线上比较的命令（会产生 API 费用，使用新的输出目录）：

```powershell
.\run-lab.cmd batch --experiment configs/workflow-repo-single.json --catalog configs/models-workflow-comparison.json --output artifacts/repo-single-live-01
```
