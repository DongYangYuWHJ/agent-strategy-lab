# Plan 20 · 任务路由与架构选择

审查 Router 的试跑遇到了验证瓶颈。现有任务和对照配置下，三组均为 3/3 通过，按需组又全部触发了 Sol 审查，其中一次只由测试引用格式触发。这批数据能说明升级行为和开销，但无法有效检验审查能补救哪些失败，也无法检验 Router 能否识别这些情况。因此先转向任务 Router，研究能否在规划前选择合适的架构，并在不同难度的任务上兼顾通过率和总费用。[Plan19 审查 Router 结果](019-task-and-review-routers.md)

状态：实现和离线验证已完成，付费对照运行中。

## Structure Router 首轮对照

Structure Router 已接入批次入口。Luna 在规划前读取原始任务、可编辑路径和简短文件清单，返回一个候选架构 ID、理由和风险。运行器校验 ID，并在同一账本下启动对应流程。路由失败时保留已发生的费用和停止原因。分档标签只进入汇总，LiveCodeBench 描述中的难度标题在路由请求中移除。

候选路径为 Luna 单体、Luna 规划后交给 Luna，以及 Sol 规划后交给 Luna。固定参照组始终采用 Sol 规划后交给 Luna。两组各跑同样八题一次，共十六个位置，配置上限为 5 美元。

| 汇总档位 | 任务 |
|---|---|
| 低 | Geometric Sequence、分页边界 |
| 中 | Gravity、游标分页 |
| 高 | Plan16 的令牌迁移、签名组合、缓存原子更新、缓存组合 |

每次路由决定保存为 `structure-routing.json`。批次报告按档位和组别分别列出通过、有效验收、路由费用及整段费用。配置与固定回复验证完成，付费对照待运行。

[实验配置](../../configs/workflow-structure-router-comparison.json) · [路由实现](../../src/agent_lab/structure_router.py)

## 付费启动记录

首次启动完成一次 Luna 路由调用，估算费用为 0.000141700 美元。旧权限审计将审计前已完成的路由调用当成 OpenCode 提前生成，首题在实施前停止，无有效验收。修复后，审计检查的是审计期间是否出现新增生成调用。权限与路由相关的 8 项本地测试通过。

新批次从原 5 美元上限扣除首笔费用，剩余额度为 4.999858300 美元。重新启动后，首题通过 OpenCode 权限审计并进入规划阶段。[首次记录](../../artifacts/plan20-structure-router-live-01/live/batch.json) · [当前批次](../../artifacts/plan20-structure-router-live-02/live/batch.json)
