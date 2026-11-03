# AI 架构实验平台

第一版用于复用同一套任务、工具、验收和用量记录，比较单个 Agent 的模型候选。模型初筛就是第一轮单 Agent 对照实验。

已实现：独立任务副本、单 Agent 工具循环、公共验证与独立最终验收、简单督察、停止条件、Token 与费用估算、批次汇总及批次续跑。

原生实验批次接受 `single_agent` 配置。OpenCode 2.0.32 后端支持固定用户工作流、主／子会话、统一费用准入与独立验收；交互启动入口继续保留。[工作流操作与配置](docs/workflow-experiments.md)。

```powershell
.\run-lab.cmd validate --experiment configs/workflow-single.json
.\run-lab.cmd batch --experiment configs/workflow-single.json --output artifacts/workflow-deepseek-01
```

此配置实际运行 DeepSeek 在一道现有调参题上的四轮会话，每轮可能包含多次模型调用，整段预算 $0.20。修改轮次消息用 `configs/workflows/daily-review.json`；修改题目、架构和预算用 `configs/workflow-single.json`；模型参数继续放在模型目录中。`--output` 使用新目录；未知用量或中断不会自动重试。

[实验决策与计划变更记录](docs/experiment-decisions.md) 只记录整体实验计划、方法或架构方向的实质变化，例如引入调参集与保留评估集。日常调参、常规修复和补充同类任务不单独新增记录，参数与结果由运行快照和报告保存。

## 在这台 Windows 电脑上开始

模拟演示无需第三方包。真实模型目录现启用匹配模型的输入 Token 计数；DeepSeek 的本地计数需要分词依赖，本机已安装在项目 `.venv` 中。入口优先使用项目 `.venv`，否则使用现有 Codex Python 运行时或系统 Python 3.11+。在其他电脑首次准备：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[token-counting]"
```

在项目目录运行：

```powershell
.\run-lab.cmd validate
.\run-lab.cmd demo
```

`validate` 只检查配置。`demo` 使用固定回放，完成三个小任务，并演示三个无进展任务被停止；没有 API 调用，没有真实 API 费用。报告中的模拟 Token 和费用仅用于验证统计流程，不能用于模型能力排名。

每个批次保存 `report.md` 和可分析的 `report.json`。本次首次试跑报告位于 `artifacts/first-demo/report.md`；后续 `demo` 默认创建新目录。

## 使用 OpenCode 交互原型

已安装 OpenCode **2.0.32** 时，在 Windows PowerShell 的项目目录运行：

```powershell
.\run-lab.cmd opencode-doctor
.\run-opencode.cmd
```

第一条核对版本、模型目录和三个项目角色，不提交模型任务。第二条打开交互终端，默认由 Sol 协调，再把一个明确的实现任务交给 DeepSeek。它读取现有 `settings.local.json`，只向子进程注入 OpenAI 和 DeepSeek 密钥，不需要重复填写或保存到 OpenCode 公共配置；发出聊天任务后会产生 API 费用。

目前只验证了配置与角色加载，尚未验证 OpenCode 的真实委派、代码修改、独立验收与完整费用归集。原生 runner 的预算和报告不会自动覆盖这个交互终端。下一步应在独立任务副本中做小规模接入试验，记录主会话、子会话及辅助模型费用，再接入批次比较。详见 [OpenCode 接入说明](docs/opencode.md)。

## 第一轮真实模型初筛

2026-11-02 新增 [九个纯 Python 工程任务候选](docs/task-calibration.md)，覆盖 TinyDB、ItsDangerous、Cachetools 的六个专项和三个组合需求。现有 Windows＋Python 即可执行，无需额外服务；39 组离线对照通过。首轮 18 项付费筛查已完成：DeepSeek 8/9、Luna 5/9，共估算 $0.686221370；每格一次，尚未作稳定性验证或 Sol 对照。配置入口为 `configs/workflow-python-calibration.json`。

已加入一个独立的 [LiveCodeBench 单 Agent 任务集](docs/livecodebench.md)：easy、medium、hard 各两道，保留 19 个公开用例和 240 个隐藏用例。配置为 `configs/livecodebench-single.json`，不改变下面原有三道演示任务的默认清单。可以先用 `validate`、`list-tasks` 与 `audit-livecodebench` 离线检查；这些检查命令不调用模型。

扩充版位于 `benchmarks/livecodebench-v2/`：共 18 题，各难度六题，分为原六题校准、新六题调参与新六题保留评估。`configs/livecodebench-development.json` 选择校准＋调参的 12 题；`configs/livecodebench-holdout.json` 只选择六道保留题。新增任务未运行付费模型实验。单次输出额度在 `configs/models.json` 的各模型 `max_output_tokens` 字段调整；整题累计额度在实验配置的 `limits.max_total_tokens` 调整，详见上述说明。

`configs/models.json` 保存七个候选模型及价格来源；`configs/screening.json` 自动扫描 `tickets/*/task.json`（目前三个任务）、一次重复、固定随机运行顺序，批次预算为 5 美元、单次预算为 1 美元。这是流程试跑配置，不足以证明能力排名。价格资料记录于 2026-10-10，执行前应重新核对。

API 密钥支持项目根目录的 `settings.local.json`。这台电脑已创建空文件；新克隆的项目先复制 `settings.example.json` 为 `settings.local.json`，再填写对应的 `api_key`：`openai` 是 OpenAI API，`deepseek` 是 DeepSeek，`anthropic` 是 Claude API。同一供应商的多个模型共用密钥；未使用的供应商留空。

本地密钥文件已加入 Git 忽略规则，空白示例可以提交。密钥独立于模型目录，不进入冻结配置、提示词或请求／响应日志，也不注入验收子进程环境；供应商接口通过 HTTPS 请求头使用它。文件仍是本地明文，Git 忽略不提供加密或 OS 隔离，当前检查进程的宿主权限限制仍然适用。

环境变量优先于本地文件：OpenAI 使用 `OPENAI_API_KEY`，DeepSeek 使用 `DEEPSEEK_API_KEY`，Anthropic 使用 `ANTHROPIC_API_KEY`。这样自动化运行可以沿用环境变量。本地文件不修改系统环境变量；框架不自动读取 `.env`。不要把密钥写进任务、模型目录或版本库。若密钥曾被提交，Git 忽略不会删除历史内容，需在供应商侧撤销旧密钥。

填写后可检查状态，不发送 API 请求，也不显示密钥：

```powershell
.\run-lab.cmd check-settings
```

它只验证配置存在且格式正确，密钥有效性、余额和模型权限需在线试跑确认。OpenAI API 账户／密钥与 ChatGPT 网页订阅的使用方式不同；此框架使用 OpenAI API 密钥。Claude 使用 Claude Console 的 API 密钥。

配置好相应密钥后，可先只运行两个廉价候选：

```powershell
.\run-lab.cmd batch --models deepseek-flash,gpt-6-luna --output artifacts/screening-01
```

运行全部候选：

```powershell
.\run-lab.cmd batch --output artifacts/screening-all-01
```

运行单个任务：

```powershell
.\run-lab.cmd run --task tickets/clamp-boundaries/task.json --model gpt-6-luna
```

密钥缺失时会在发送请求前报错；没有自动重试网络请求。2026-10-12 已用真实 API 验证 `deepseek-flash` 和 `gpt-6-luna`，2026-10-13 单独验证了 `claude-haiku-5-5`：三者均完成 clamp-boundaries 的工具循环、公共检查和独立最终验收，保存了供应商用量。其他候选模型仍待在线验证。单任务试跑不构成能力排名。

首次接入可使用 `configs/connectivity.json`：一个固定任务、两个候选、最多 8 次调用、单次估算费用准入预算 0.25 美元、批次预算 0.50 美元。也可以只选一家的模型；请使用新的输出目录：

```powershell
.\run-lab.cmd batch --experiment configs/connectivity.json --models deepseek-flash --output artifacts/connectivity-deepseek-02
.\run-lab.cmd batch --experiment configs/connectivity.json --models gpt-6-luna --output artifacts/connectivity-openai-02
```

两家分别运行时，各自使用独立批次账本；各一次运行的准入预算合计 0.50 美元，仍不等同于供应商账单硬上限。2026-10-12 的原始记录位于 `artifacts/connectivity-20261012-01/`。

Claude 可单独使用 `configs/claude-connectivity.json`：Haiku 5.5、同一个固定任务、一次运行、整批估算费用准入预算 0.05 美元。2026-10-13 的报告位于 `artifacts/connectivity-claude-20261013-01/report.md`。

```powershell
.\run-lab.cmd batch --experiment configs/claude-connectivity.json --output artifacts/connectivity-claude-02
```

## 同模型同任务的费用浮动

`configs/cost-variance.json` 固定一个任务，DeepSeek Flash 与 OpenAI Luna 各重复 5 次；总计 10 次运行。每次重置源码与对话，保持供应商默认缓存行为，运行顺序随机打乱。单次估算费用准入预算 0.05 美元、整批 0.50 美元；其他停止条件沿用连通性试跑。

```powershell
.\run-lab.cmd batch --experiment configs/cost-variance.json --output artifacts/cost-variance-01
.\run-lab.cmd variance-report --input artifacts/cost-variance-01
```

第一条会调用真实 API，第二条只分析保存的数据。`variance.md` 与 `variance.json` 按任务和模型分别报告最低、中位、最高费用、相对中位数范围、样本变异系数、调用数、Token、缓存比例和逐次数据。失败尝试保留；费用未知时不计算该组费用波动。

报告还按同次真实用量，将所有输入按未缓存价格重算一个反事实参考，以帮助分辨执行量和缓存计价差异。这个数值不是供应商账单，也没有额外发送 API 请求。缓存可能跨运行复用，重复运行不保证统计独立；5 次样本只描述本次范围，不用于估计稳定的 P90/P95 或整体模型能力。

## 停止与续跑

当前默认限制：12 次模型调用、30 次工具调用、首次提交之后最多 2 轮修复、连续 2 次同样的失败且源代码未变时停止、总 Token 100000、单次运行 180 秒、单次检查 15 秒。

所有修复共用同一份运行额度；整个批次也累积费用。供应商未返回有效用量或网络结果不明时，停止该运行和后续批次调用，不会把未知用量记成零。

```powershell
.\run-lab.cmd batch --models deepseek-flash,gpt-6-luna --output artifacts/screening-01 --resume
.\run-lab.cmd report --input artifacts/screening-01
```

续跑要求任务、代码、验收、模型配置、价格、提示词和框架内容都与原批次一致。已结束的实验单元不会重跑。完整结果已保存、批次清单尚未来得及更新时，会恢复映射。

若有运行只留下部分记录，框架会重建已知费用和未完成请求的预留并生成报告，然后拒绝自动重跑。需要先核对该运行与供应商账单；本版不提供在途对话自动接续，也不宣称能恢复网络中断前的模型状态。

## Token 和费用的含义

- 真实用量来自供应商响应，保留原始响应与逐调用记录。
- 总 Token = 输入 + 输出。缓存读取／写入是输入的子集；推理 Token 是输出的子集，不重复相加。
- 费用 = 归一化后的用量 × 本批次保存的价格。它是估算费用，不是供应商实付账单。
- DeepSeek 第一版统一使用峰时价格保守估算；非峰时真实账单可能更低。长上下文阶梯、Fast／Flex／Batch、区域加价与服务端付费工具尚未支持。
- 请求体传输上限与输入 Token 预留分开：默认请求体最多 1 MiB，预留输入最多 64000 Token。模型目录的 `token_counting: "model"` 启用匹配计数：DeepSeek 使用固定版本的官方 V4.1 文本分词文件和对话模板，本地包含工具和推理历史；OpenAI／Claude 使用各自的官方输入计数接口。计数后加 `limits.token_count_margin`（默认 256），再加本次最大输出检查整题 Token 与金额预算。原始续接信息完整保留，实际用量仍只取生成响应的 usage，不把计数结果当作已消耗 Token。
- `token_counting: "estimate"` 保留旧的保守估计方式，供明确选择的旧配置／模拟使用；匹配计数失败时记录 `input_count_error`，不静默退回旧估计，不发送该次生成请求、不重试，并停止批次。计数调用有单独的 30 秒超时和事件记录，不计为生成调用次数；网络延迟计入整题运行时间。固定 tokenizer 版本、摘要和计数方法写入运行／批次快照，实际计数与生成 usage 的差异写入事件。计数与余量仍不能保证精确的最高账单或所有模型的价格阶梯边界。
- 供应商明确报告输出额度耗尽时，记录 `output_token_limit`，保留已花用量，不执行部分工具调用、不当成提交、不消耗修复次数，也不自动重试。请求体超限与估计输入超限分别记录 `request_size_limit`、`input_estimate_limit`。
- 调用次数、工具步骤和修复次数由框架控制；运行时间在阶段切换时检查，并用于网络／检查超时。单次 API 请求等待上限由实验配置的 `limits.request_timeout_seconds` 控制，目前为 300 秒（5 分钟）；单任务 `run` 默认读取 `configs/limits.json` 的同名字段。整题剩余时间不足时，以剩余时间为准。供应商端已在途的推理无法由本地框架保证取消。
- 未知费用预留单独列出；有未知用量时，单位合格交付成本显示“费用不完整”。

单位合格交付成本包括失败尝试：所有尝试的估算费用 ÷ 合格交付次数。没有成功交付时显示“无合格交付”。模拟与真实结果永远分组统计。

## 新增任务

在 `tickets/` 下新增一个文件夹，例如 `tickets/new-task/`，使用下面的结构，并给 `task.json` 设置唯一的 `id`：

```text
task.json            需求、验收条件、可编辑文件
source/              初始代码
public_check.py      给执行者反馈的检查
final_check.py       仅用于最终验收的检查
replay.json          仅离线模拟需要的固定动作
```

默认初筛配置会自动发现新任务，不需要修改 Python 代码或逐个添加任务名称。扫描规则在 `configs/screening.json` 中：

```json
"task_globs": ["../tickets/*/task.json"]
```

路径相对于实验配置文件所在目录。`*` 匹配一层任务文件夹；如果按类别再分子目录，可改用 `../tickets/**/task.json` 递归扫描。

先预览完整列表，再启动实验：

```powershell
.\run-lab.cmd list-tasks
.\run-lab.cmd list-tasks --json
.\run-lab.cmd validate
```

`--json` 输出自动生成的任务数组；这些命令不调用模型。批次启动时，程序按发现的任务列表建立“任务 × 模型 × 重复次数”的运行清单，再自动分发。

正式实验需要固定样本时，可以使用显式 `tasks` 数组代替扫描；`configs/demo.json` 就保留三个固定回放任务，以免新增真实任务后，演示意外要求其拥有模拟回放。两种方式可以组合，同一路径只加载一次；不同任务不能使用同一个 ID。扫描无匹配、清单无效或源码／检查缺失都会在模型调用之前报错。

每次批次把发现的任务路径、任务指纹与运行清单保存到 `batch.json`。新增、删除或修改任务后，应启动新批次；续跑会拒绝改变原来的样本集。

检查程序是操作者提供的独立 Python 文件，从 `LAB_WORKSPACE` 定位本次代码副本。检查通过要求退出码 0、与本次调用绑定的正常完成记录、以及可信评分程序对实际结果的核验；只有退出码或“成功”输出不会被当作通过。退出码 1 表示任务失败，2 表示检查环境错误；提前退出但没有完成记录会被拒绝。检查文件必须位于 `source/` 外面。

现有函数任务使用 `check_client.load_submission` 在另一个进程中调用被测代码；标准输入输出任务由可信 host 比较子进程的实际输出。自定义检查应沿用这种分离方式，避免把被测代码直接导入评分进程。运行辅助代码随每次检查复制并验证摘要。

执行者可以读任务源码、修改明确列出的文件，不能通过文件工具读取或修改验收程序。最终验收结果不会回灌模型进行重试；公开检查允许有限修复。每次验收前后检查不可编辑文件及验收脚本的完整性。

第一版提供文件列表、读取、字面搜索、完整文件写入、运行公共检查和提交六个工具；不提供任意 shell 命令。大文件读取会截断，单次写入最多 64000 字节，源码单文件最多 1 MB，不支持符号链接。

**当前工作环境是目录副本隔离，尚未接入容器或 OS 沙箱。** 检查会执行生成的 Python 代码，子进程不继承 API 密钥，但仍具有宿主用户的其他权限。先使用受信任的小型任务；要扩展到不可信代码或正式仓库评测，需要接入进程／容器隔离。文件工具的限制不能替代 OS 沙箱。

## 运行记录

```text
artifacts/<batch>/
  batch.json               冻结配置、运行顺序、完成清单
  report.md / report.json  结果汇总
  runs/<run-id>/
    config.json            模型、价格、工具、提示词及版本指纹
    task.json              公共任务定义
    baseline/              原始代码副本
    workspace/             该次运行代码
    checks/                独立检查副本与检查日志
    calls/                 每次请求、响应（不保存鉴权头）
    events.jsonl           阶段、工具、调用、验证事件
    state.json             最近状态与累计消耗
    changes.patch          代码差异
    delivery.json          提交说明与验收证据（有最终提交时）
    result.json            最终结果和停止原因
```

原始轨迹会包含任务代码和供应商返回的内容，按项目数据管理。配置固定的是 API 模型名称与调用参数；如果供应商没有提供版本快照，固定别名不能保证底层权重不变，因此同时记录返回模型和响应 ID。

## 工程结构与测试

公共数据约定、费用账本、供应商接口、工作环境、工具、验收、策略、协调器和报告分别位于 `src/agent_lab/`。详见 [架构与约定](docs/architecture.md)。

测试不调用任何真实 API：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

适配器实现依据：

- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)：Responses 工具调用、工具结果与推理块延续。
- [DeepSeek tool calls](https://api-docs.deepseek.com/guides/tool_calls/) 和 [Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)：工具循环、思考内容及用量。
- [Claude tools](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools) 和 [Messages](https://platform.claude.com/docs/en/api/messages/create)：工具块、结果块与缓存用量。
