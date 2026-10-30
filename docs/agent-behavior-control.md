# 怎样控制 Agent 行为：规划后交接示例

本项目新增策略 `planner_handoff`：同一 OpenCode 会话第一轮由 Planner 规划，正常结束后将主角色和模型切换为 Executor，后三轮直接由 Executor 处理。Planner 不再介入，不创建子会话，也没有智能 Router。

## 1. 实验配置选择结构、模型和预算

入口：[configs/workflow-planner-handoff.json](../configs/workflow-planner-handoff.json)。核心配置：

```json
{"id": "sol-handoff-deepseek", "strategy": "planner_handoff", "models": ["gpt-6.1-sol", "deepseek-flash-executor-low"]}
```

- `strategy` 选择运行逻辑；不是随意给结构起名，运行器必须实现相应策略。
- `models[0]` 为 Planner，`models[1]` 为 Executor。这里是模型目录的 ID，不是供应商密钥。
- `limits` 是整段会话的共享预算，交接后不重置。模型输出额度、推理档位和价格见指定的模型目录。
- `workflow` 指向 [四轮用户消息](../configs/workflows/daily-review.json)，不把额外交接提示插入用户对话。

本配置含两个结构：Sol→DeepSeek、Sol→Sol，各使用同样的简单／中等／困难三题，共六例，每例一次、上限 $0.50，批次上限 $3.00。配置通过不等于线上已经运行。

2026-10-27 调参后，整段会话 `max_total_tokens` 为 200000，单次 `max_output_tokens` 仍为 16384。DeepSeek 使用独立目录项：`deepseek-flash-planner-max`（`reasoning_effort=max`）和 `deepseek-flash-executor-low`（`reasoning_effort=low`）；两者实际调用的仍是 `deepseek-flash`。原 `deepseek-flash` 目录项保留供单 Agent 使用。`low` 已是开启思考时的最低档，`none` 才是关闭思考；本次没有关闭思考，也没有改变 Sol 档位。相同改动已应用到其他 Planner／Executor 实验入口；独立单 Agent 实验入口不变。修改后必须用新输出目录，不能继续旧批次。

只检查配置、不运行模型：

```powershell
.\run-lab.cmd validate --experiment configs/workflow-planner-handoff.json --catalog configs/models-workflow-comparison.json
```

## 2. 角色文件定义职责

- [workflow-handoff-planner.md](../roles/workflow-handoff-planner.md)：读取需求、提供关键方案和验证条件；不实现、不委派、不参与后续复核。
- [workflow-handoff-executor.md](../roles/workflow-handoff-executor.md)：读取会话中的已有方案，直接面向用户实施、检查和修正；不向 Planner 回报或委派。

这些内容由程序写入 OpenCode Agent 的 `system` 字段。修改文件会改变模型收到的职责提示，并被冻结到运行快照；旧批次不能在改动后继续运行。提示词表达期望，不是强制权限。

## 3. OpenCode 配置与权限规定能做什么

[opencode_config()](../src/agent_lab/opencode_workflow.py) 根据实验配置生成每次运行的 `workspace/opencode.jsonc` 和可查阅副本 `opencode-config.json`。本策略的关键结构是：

```jsonc
{
  "default_agent": "lab-experiment-planner",
  "agents": {
    "lab-experiment-planner": { "mode": "primary" },
    "lab-experiment-executor": { "mode": "primary" }
  }
}
```

这里只展示角色入口；实际生成文件还包括每个角色的 `model`、`system`、`permissions`、供应商网关和 MCP 配置，不能把上面片段当成完整实验配置。

[opencode_permissions.py](../src/agent_lab/opencode_permissions.py) 对两个角色均先拒绝全部权限，再允许自身 MCP 工具：Planner 没有写入工具；Executor 可以在可写轮次修改白名单文件；两者均不能委派。启动时读取实际注册角色，并调用 OpenCode 权限接口检查，防止已有配置额外放行工具。

根目录交互用的 `opencode.jsonc` 与旧角色文件保持原样。本策略的修改只用于专用实验配置。

## 4. 运行器决定何时切换

[OpenCodeSession.select_primary()](../src/agent_lab/opencode_workflow.py) 在会话空闲且没有排队输入时：

1. 读取当前会话 Agent 和模型。
2. 必要时调用 `POST /api/session/{id}/agent` 设置 Executor。
3. 必要时调用 `POST /api/session/{id}/model` 设置执行模型。
4. 重新读取同一会话，核对会话 ID、角色和模型；不匹配就停止，不发送下一轮。

这些是本机 OpenCode 的控制请求，不是模型生成请求。只修改 `default_agent` 不会切换已有会话；仅把角色写为 `primary` 也不会自动切换。

第一轮失败时不切换。后续 Executor 遇到阻塞则如实停止，本策略不自动召回 Planner。保留原会话历史和工作区，不额外调用模型写交接总结。

网关另按阶段限制允许的模型和 MCP 角色；规划轮禁止写入，所有轮次共用账本。每轮 `selection.json` 保存角色／模型读回证据，`turn.json` 保存实际选择及累计用量，`events.jsonl` 的请求事件记录阶段角色。即使两角色使用同一模型，也按轮次记录，不能只按模型名称推断职责。

## 5. 验证与线上入口

本机固定回复检查已经确认同一会话保留规划历史、没有子会话、四轮最终验收通过，以及不安全权限在零生成时被拒绝。这是运行机制验证，不是模型能力或省钱结论。

136 项本地回归通过，覆盖交接失败停止、共享预算、角色与模型限制等；[验证汇总](../artifacts/handoff-verification-20261027.json) 保存本机协议检查入口。这些本机证据位于被 Git 忽略的 `artifacts/`。

以后决定运行线上六例时使用以下命令；本次实现没有执行它：

```powershell
.\run-lab.cmd batch --experiment configs/workflow-planner-handoff.json --catalog configs/models-workflow-comparison.json --output artifacts/planner-handoff-live-02
```

官方接口：[OpenCode V2 API](https://opencode.ai/v2/docs/api)。本机验证版本为 2.0.32。
