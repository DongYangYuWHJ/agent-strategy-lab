# 通用 prompt 工作流实验

目的：模拟日常使用中的复核与跟进，在相同交互条件下比较架构的最终质量、总费用和耗时，不研究 prompt 措辞有效性。先复用开发／调参题；算法题仍不能代表完整的真实仓库开发能力。

## 运行与配置

```powershell
.\run-lab.cmd validate --experiment configs/workflow-single.json
.\run-lab.cmd batch --experiment configs/workflow-single.json --output artifacts/workflow-deepseek-01
```

- `configs/workflows/daily-review.json`：四轮消息及每轮是否允许改代码。
- `configs/workflow-single.json`：任务清单（tasks／task_globs）、架构、工作流路径、重复次数和预算。
- `configs/models.json`：输出上限、推理档位、计数方法和冻结价格。
- `settings.local.json`／环境变量：密钥，不进入配置快照或 OpenCode 子进程。

不同输出目录表示独立运行。批次 `--resume` 只继续未开始的任务，不重放中断案例；任务、工作流、架构、模型、代码、检查或计数版本改变时拒绝续跑。

## 四轮执行

| 轮次 | 用户交互 | 权限 |
|---|---|---|
| plan | 原始任务＋阅读、说明方案 | MCP 写入在代码层拒绝 |
| implement | 复核方案，考虑更简单的方法，再实施和检查 | 可修改白名单文件 |
| requirements-review | 核对是否覆盖原始需求 | 可修正，也可保留 |
| verification-review | 核实测试范围、证据和完成声明，交付 | 可检查和必要修正 |

任务只在首轮注入，后续继续同一主会话和代码目录。程序等待主会话针对当前输入的结束事件；消息入队、工具完成和子角色返回均不算用户回合完成，不用文字“我确定”判断正确性。

全部回合结束后运行独立公开／隐藏验收。公开检查工具可在工作中使用，隐藏结果不反馈，也不决定是否追加追问。每轮保存消息、事件、代码快照和累计账本，不逐句评分。需要澄清时可调用 `request_clarification`，保留问题并停止为 `needs_user_input`，不编造回答。

## OpenCode 和资源控制

固定版本 2.0.32。实验目录生成专用配置，通过本机 MCP 暴露文件白名单工具、公开检查和澄清。实验使用独立角色名，每个角色先拒绝全部权限，再逐项允许自身 MCP 工具及必要委派；原生读写和 shell 等工具不开放。发送任务前，程序检查实际注册的角色、模型、指令和权限，并通过 OpenCode 权限接口核对实际判定；失败则以 `permission_configuration_error` 停止，不开始模型生成，证据写入 `permission-audit.json`。旧交互配置保持原样。

此修复针对 2026-10-26 发现的旧角色原生 edit allow 继承问题；当时执行者曾使用原生 patch，历史结果未重跑，发现和本机正反检查见 [011](decisions/011-planner-executor.md)。MCP 按轮次和文件白名单限制写入，原始题目未被覆盖；这些工具权限控制不等于 OS 沙箱。

OpenCode 通过本机网关使用 DeepSeek Chat Completions、OpenAI Responses、Claude Messages 原生协议。密钥只由父进程持有。网关逐次做 Token／费用／时间／调用额度准入，执行目录中的输出与推理配置，记录流式响应和真实 usage。输出先缓存在网关，计量完成且未截断后才交给 OpenCode 执行工具。

全部轮次、子角色和辅助生成共用同一账本。工具额度涵盖响应中的原生交接工具和 MCP 调用，MCP 执行不重复计数。网关停止后不再请求供应商；OpenCode 内部重试不会再次请求上游。未知用量或计数错误暂停批次。费用是冻结价格下的估算，不是账单保证。

缓冲会影响首个输出的呈现时机；本实验统计总耗时，不测首字延迟。计数请求时间计入耗时，不作为生成 Token 用量。

## 架构配置

`architectures` 每项包含唯一 id、strategy 和有序 models 列表。例如：

```json
[
  {"id": "deepseek-solo", "strategy": "single_agent", "models": ["deepseek-flash"]},
  {"id": "fable-deepseek", "strategy": "planner_worker", "models": ["claude-fable-5-1", "deepseek-flash"]}
]
```

此例只说明语法；加入数组会增加实际运行，不是当前配置默认内容。planner_worker 的第一个模型为对外规划者，第二个为执行者。消息只发给规划者；它可读代码、核对公开检查和委派，不能直接写代码。执行者可修改白名单文件，不能继续委派。规划轮的 MCP 写入限制对所有角色生效。对应角色名为 `lab-experiment-planner` 和 `lab-experiment-executor`；单 Agent 使用 `lab-experiment-solo`。

Sol Planner＋DeepSeek Executor 及两组单模型对照的专用入口为 `configs/workflow-planner-executor.json`，配合 `--catalog configs/models-workflow-comparison.json`。配置检查：

```powershell
.\run-lab.cmd validate --experiment configs/workflow-planner-executor.json --catalog configs/models-workflow-comparison.json
```

角色指令在 `roles/workflow-planner.md` 与 `roles/workflow-executor.md`。程序把其完整内容冻结到批次和运行快照，修改后拒绝续跑旧批次；每例 $0.50，每批三例 $1.50。后续配置 `configs/workflow-planner-executor-variants.json` 增加了 DeepSeek→Sol、DeepSeek→DeepSeek、Sol→Sol，各一次；连同原 Sol→DeepSeek，四种搭配三种通过、一种请求澄清暂停。全部数据与权限继承问题见 [011](decisions/011-planner-executor.md)。中等／困难任务仍待测试。

## 记录与验证

报告输出 `report.md`、`report.json`，按 backend、workflow、strategy、模型组合分组，包含最终验收、完成轮次、Token、费用、耗时和停止原因。native 后端旧分数不直接作为 OpenCode 对照。

每次运行保留冻结配置、事件、原始请求响应和 SSE、`turns/*/turn.json`、轮末代码和消息、主／子会话导出、源码差异与验收证据。完整导出补充消息分页之外的轨迹；目录被 Git 忽略。

本地测试覆盖顺序、写入权限、跨轮预算、失败关闭、验收时机和报告分组。`tests/opencode_protocol_check.py` 是本机 OpenCode 协议检查，使用固定回复，不消耗供应商生成额度，结果标记 simulated。线上效果以真实报告为准。

接口依据：[API](https://opencode.ai/v2/docs/api)、[权限](https://opencode.ai/v2/docs/permissions)、[供应商配置](https://opencode.ai/v2/docs/providers)、[MCP](https://opencode.ai/v2/docs/mcp-servers)。现已完成三家供应商的五种单 Agent 模型线上检查，见文末；四种双角色线上尝试及权限修复后一次 Sol→DeepSeek 线上检查见 011，其余组合尚未在修复后重跑。

## 首次线上检查：2026-10-24

仅运行一次：DeepSeek Flash，Happy New Year 2025，四轮全部完成。共 9 次生成、6 个工具调用，26960 Token，27.0 秒，估算费用 $0.003858156，用量完整。公开用例 4/4、隐藏用例 40/40 通过；规划轮源码保持不变，隐藏验收在第四轮结束后进行。

本轮 OpenCode 请求的本地输入计数均比供应商报告多 40 Token；保留的 256 Token 余量之外还多预留了这 40，不影响实际 usage 计费。该差异原样记录，未修改计数或重跑。不能沿用此前原生请求逐次计数完全一致的结论。

证据：[线上报告](../artifacts/workflow-deepseek-20261024-01/report.json)、[本地 OpenCode 固定回复检查](../artifacts/workflow-protocol-20261024-03/report.json)。本轮证明单 Agent 工作流接入可用，不据此推断多 Agent 效果或模型排名。

## 五模型单 Agent 验证：2026-10-24

同一题、同一四轮工作流，DeepSeek／Luna／Sol／Sonnet／Haiku 各运行一次，全部完成四轮并通过公开 4/4、隐藏 40/40，用量完整，未重跑。批次共 131689 Token，冻结价格下估算费用 $0.063397832。单题单次结果用于确认接入和观察开销，不作为稳定排名。

配置为 `configs/workflow-model-comparison.json`，配合 `--catalog configs/models-workflow-comparison.json`；每模型上限 $0.50，整批 $2.50。费用明细见 [比较报告](../artifacts/workflow-model-comparison-20261024-01/cost-comparison.md)，简要结论已补入 [010](decisions/010-conversation-workflow-evaluation.md)。
