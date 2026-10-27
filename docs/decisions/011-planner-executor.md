# 011：Planner＋Executor 对照实验

建立：2026-10-25；更新：2026-10-26。已完成初轮单题试跑、权限修复及三层任务比较：6 种配置各跑简单／中等／困难一题，共 18 例、11 例最终验收通过。已记录分工开销；额度、澄清路径及职责重叠仍待研究，初轮历史结果保留。

## 初轮目标与固定条件

在相同用户交互下比较独立执行与规划／执行分工的质量、费用和耗时。箭头为 Planner → Executor；Planner 接收四轮消息、规划及复核，Executor 实现和回报。使用 OpenCode 原生 subagent、共享源码副本和总账，最后独立验收；不增加投票督察或递归委派。

- 任务：Happy New Year 2025（lcb-abc387-a）；四轮：规划 → 实施 → 需求复核 → 测试与交付声明复核。
- 每例：最多 20 次生成、40 次工具、100000 Token、900 秒；单次请求 300 秒；费用上限 $0.50。两个批次各自上限 $1.50。
- 输出上限均为 16384；Sol 为 medium、DeepSeek 为 low，沿用原有模型设置。同名跨供应商档位不保证等价。
- 两批的任务、运行器、四轮工作流、限制指纹一致，四种协作组合的角色指令也一致；各架构各一次，未调参重跑，保留评估集未使用。

## 初轮单题结果

A 为 2026-10-25 的原三组，B 为 2026-10-26 的新增三组。完成验收的各组均公开 4/4、隐藏 40/40 通过；暂停组只完成前三轮、此前公开检查通过，隐藏验收未执行。

| 架构 | 批次 | 轮次 | 最终结果 | 调用 | 总 Token | 估算费用 USD | 耗时秒 |
|---|---|---:|---|---:|---:|---:|---:|
| DeepSeek 单 Agent | A | 4/4 | 通过 | 9 | 28663 | 0.004429068 | 29.750 |
| Sol 单 Agent | A | 4/4 | 通过 | 11 | 20185 | 0.015511000 | 39.593 |
| Sol → DeepSeek | A | 4/4 | 通过 | 14 | 35808 | 0.023533664 | 47.172 |
| DeepSeek → Sol | B | 3/4 | 暂停：请求澄清 | 16 | 60566 | 0.020927540 | 52.875 |
| DeepSeek → DeepSeek | B | 4/4 | 通过 | 17 | 69713 | 0.012900276 | 66.422 |
| Sol → Sol | B | 4/4 | 通过 | 14 | 31639 | 0.028102000 | 55.282 |

四种 Planner＋Executor 合计 **197726 Token、$0.085463480**，含暂停尝试的消耗；本次新增三组为 $0.061929816。加上表中两组单 Agent 对照，两批共 $0.105403548，不含更早初筛。费用按供应商 usage 和冻结价格估算，DeepSeek 采用保守高峰价，不是账单。

## 初轮协作角色开销

| Planner → Executor | Planner 调用 / 费用 USD | Executor 调用 / 费用 USD | 完成委派 / 尝试 | 子会话 |
|---|---:|---:|---:|---:|
| Sol → DeepSeek | 10 / 0.022065500 | 4 / 0.001468164 | 1/1 | 1 |
| DeepSeek → Sol | 10 / 0.006827340 | 6 / 0.014100200 | 1/3 | 2 |
| DeepSeek → DeepSeek | 10 / 0.007806336 | 7 / 0.005093940 | 2/2 | 2 |
| Sol → Sol | 10 / 0.021137100 | 4 / 0.006964900 | 1/1 | 1 |

同型号仍是独立主／子会话。每次生成通过响应 ID 或完整用量＋请求时间唯一匹配角色，角色费用之和与网关总账一致，没有把相同模型重复计费。

## 暂停与新发现

1. **DeepSeek → Sol：交接要求与工具能力不匹配。** 第四轮 Planner 要求执行者运行额外 12 组边界输入，并给出命令、stdout 和退出码，但现有工具没有任意 shell/Python 执行入口。Sol 请求澄清后，平台按现行规则暂停整段会话。不能把它记为最终通过或算法答案错误；执行者澄清直接升级为用户暂停的机制也影响了结果。停止后没有新增供应商生成。
2. **原生编辑权限继承。** 实际注册的 lab-worker 继承了原交互配置的 edit allow；DeepSeek → Sol 的执行者使用了原生 patch，而非 MCP write_file。此前“原生编辑已全部禁用、文件操作都经 MCP”的说明不准确。四种组合的规划轮快照均未修改代码，实际修改均出自 worker，但原生 patch 不受 MCP 的逐轮写入守卫拦截，不能称工具隔离已完整验证。

上述线上实验结束后的分析阶段只保留和分析结果，未修改或重跑；随后权限修复见下节。

## 权限修复：2026-10-26

- 实验角色改为 `lab-experiment-solo`、`lab-experiment-planner`、`lab-experiment-executor`；原交互角色及根目录 `opencode.jsonc` 保持原样。每个实验角色先显式拒绝全部权限，再逐项允许自身 MCP 工具；Planner 只能委派给实验 Executor，不能写入，Executor 不能继续委派。
- 发送任务前读取实际注册的角色、模型、指令和权限，并调用 OpenCode 权限接口逐项核对。发现额外放行或实际判定不符，即以 `permission_configuration_error` 停止，保存 `permission-audit.json`，不开始模型生成。规划轮的 MCP 写入守卫继续对全部角色生效。
- 129 项回归通过。本机 OpenCode 2.0.32 使用固定回复完成单 Agent／双角色四轮和最终验收；确认旧配置仍被加载、原生编辑工具未暴露给模型，双角色确实通过原生 subagent 委派并经 MCP 写入。故意追加原生编辑许可时，在第零轮被拒绝，模型请求为零。固定回复结果标记为 simulated，没有付费生成，也不作为模型能力数据。
- 权限修复只改变权限边界，未改变澄清路由、任务、额度或价格；先前线上费用和成绩保留。执行者工具不足时的回报／澄清路径仍待处理；权限修复阶段尚未开始中难题。

证据：[回归记录](../../artifacts/permissions-fix-20261026/regression.txt)、[单 Agent 检查](../../artifacts/permissions-fix-solo-protocol-20261026-02/lcb-abc387-a-deepseek-flash-91e6a34fafe4/fixture-assertions.json)、[双角色权限审计](../../artifacts/permissions-fix-pair-protocol-20261026-01/lcb-abc387-a-deepseek-flash--deepseek-flash-f5977d5348ef/permission-audit.json)、[拒绝反例](../../artifacts/permissions-fix-reject-protocol-20261026-01/lcb-abc387-a-deepseek-flash--deepseek-flash-ecd037856486/permission-audit.json)。工具权限控制不等于 OS 沙箱。

随后线上检查一次：Sol→DeepSeek，原简单题、四轮、原模型与每例额度，独立批次上限 $0.50，未调参或自动重跑。四轮完成，公开 4/4、隐藏 40/40 通过；14 次生成、35555 Token、55.282 秒，估算 $0.024364920，用量完整。46 项启动权限探测通过；规划轮源码不变，只有 Executor 在实施轮经 MCP 写入一次 `solution.py`，主／子会话未出现原生编辑调用，模型收到的工具列表也未包含原生编辑或 shell。这次是正常路径验证，没有诱导真实模型越权；拒绝行为的证据来自前述本机反例。结果不并入上方历史对照表，不据此判断费用差异或稳定排名。

入口：[单次权限检查配置](../../configs/workflow-permission-smoke.json)；证据：[线上报告](../../artifacts/permissions-live-smoke-20261026-01/report.md)、[轨迹核对结果](../../artifacts/permissions-live-smoke-20261026-01/permission-verification.json)。

## 三层任务比较与开销发现：2026-10-26 补记

权限修复后，使用调参集 Geometric Sequence（简单）、Gravity（中等）、Hierarchical Majority Vote（困难），6 种配置各题一次，共 18 例。同一四轮交互、沿用原模型设置与每例总额度，未调参或重跑，未使用保留评估集。共 205 次模型生成、914441 Token，估算费用 $0.523271072。

| 配置 | 最终验收通过 / 尝试 | 单体／Planner 调用 | Executor 调用 | 合计调用 | 三题费用 USD |
|---|---:|---:|---:|---:|---:|
| DeepSeek 单 Agent | 1/3 | 25 | — | 25 | 0.046982052 |
| Sol 单 Agent | 3/3 | 30 | — | 30 | 0.077610500 |
| Sol → DeepSeek | 2/3 | 28 | 17 | 45 | 0.116507720 |
| DeepSeek → Sol | 1/3 | 19 | 13 | 32 | 0.084085908 |
| DeepSeek → DeepSeek | 1/3 | 19 | 10 | 29 | 0.057087792 |
| Sol → Sol | 3/3 | 30 | 14 | 44 | 0.140997100 |

调用指模型生成，不是 MCP 工具调用。费用包含提前停止的消耗；7 例停止为 4 例总 Token 额度预留、1 例单次输出截断、2 例工具不足请求澄清，均未执行最终验收，不能直接归为算法答错。

- **拆分职责没有自动减少主会话工作。** Sol 单 Agent 已包含规划、实施和复核，三题共调用 30 次；Sol→Sol 的 Planner 自己仍调用 30 次，再加 Executor 14 次，合计 44 次，比单体完成全部工作更多。两者均通过三题，双角色费用约为单体的 1.82 倍。这里是二者合计更多，并非每个角色分别都超过单体。
- **交接和上下文带来新增费用。** 约 84% 的费用增量发生在实施轮，该轮同时计入 Planner 交接／检查与 Executor 实施／回报。规划轮的角色指令和工具定义也更长；父子会话重复读取、检查，以及部分额外验证要求均已观察到，但各自影响尚未通过对照隔离。
- **待研究的方向**：任务是否需要更大的实际工作量和多模块结构，而非只提高算法难度；Planner 是否包办过多实现细节或重复验证。它们仍是假设，尚未修改任务或职责进行验证。每题仅一次，本批不作为稳定架构排名。

配置：[分层比较入口](../../configs/workflow-architecture-cost-comparison.json)。证据：[独立评估](../../artifacts/architecture-cost-comparison-20261026-01/assessment.md)、[逐题与精确数据](../../artifacts/architecture-cost-comparison-20261026-01/comparison.json)、[角色开销调查](../../artifacts/architecture-cost-comparison-20261026-01/role-overhead-investigation.md)。独立分析完成后，经讨论将上述表格与简要发现补入本计划。

## 阶段判断与后续

- 初轮已观察到真实主／子协作及全调用计量；成功完成验收的三种搭配，在该简单题上均比已有单 Agent 对照更贵、更慢，未观察到最终质量收益。
- 初轮四种搭配的 Planner 均生成 10 次；后续三层比较进一步观察到主会话与交接开销。缓存、服务状态与生成波动均影响费用和耗时，当前不能据此确定稳定排名。
- 权限修复与三题分层比较已完成；待研究任务工作量、角色职责与重复验证，并处理执行者工具不足时的回报／澄清路径。尚未启动新的职责对照或更大工程任务实验。

## 文件与证据

- 角色：[Planner](../../roles/workflow-planner.md)、[Executor](../../roles/workflow-executor.md)。指令全文进入批次／运行快照，变更后拒绝续跑旧批次。
- 配置：[原三组](../../configs/workflow-planner-executor.json)、[新增三组](../../configs/workflow-planner-executor-variants.json)、[冻结模型与价格](../../configs/models-workflow-comparison.json)。
- 汇总：[可读比较](../../artifacts/planner-executor-variants-20261026-01/all-planner-executor-comparison.md)、[精确数据／逐调用角色归属／交接](../../artifacts/planner-executor-variants-20261026-01/all-planner-executor-comparison.json)。
- 原始报告：[A 批次](../../artifacts/planner-executor-comparison-20261025-01/report.json)、[B 批次](../../artifacts/planner-executor-variants-20261026-01/report.json)。
- 配置阶段 13 项离线测试通过：[记录](../../artifacts/planner-executor-config-20261025/tests.txt)。该测试未覆盖实际 OpenCode 对项目旧角色权限的合并，这是此次新发现的边界。
