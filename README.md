# AI 架构实验平台

第一版用于复用同一套任务、工具、验收和用量记录，比较单个 Agent 的模型候选。模型初筛就是第一轮单 Agent 对照实验。

已实现：独立任务副本、单 Agent 工具循环、公共验证与独立最终验收、简单督察、停止条件、Token 与费用估算、批次汇总及批次续跑。

规划者＋执行者、动态升级和模型审查属于后续策略。当前只接受 `single_agent` 配置，不会偷偷调用第二个模型。

## 在这台 Windows 电脑上开始

无需安装第三方 Python 包。入口自动使用现有的 Codex Python 运行时；其他电脑可以使用 Python 3.11+。

在项目目录运行：

```powershell
.\run-lab.cmd validate
.\run-lab.cmd demo
```

`validate` 只检查配置。`demo` 使用固定回放，完成三个小任务，并演示三个无进展任务被停止；没有 API 调用，没有真实 API 费用。报告中的模拟 Token 和费用仅用于验证统计流程，不能用于模型能力排名。

每个批次保存 `report.md` 和可分析的 `report.json`。本次首次试跑报告位于 `artifacts/first-demo/report.md`；后续 `demo` 默认创建新目录。

## 第一轮真实模型初筛

`configs/models.json` 保存七个候选模型及价格来源；`configs/screening.json` 自动扫描 `tickets/*/task.json`（目前三个任务）、一次重复、固定随机运行顺序，批次预算为 5 美元、单次预算为 1 美元。这是流程试跑配置，不足以证明能力排名。价格资料记录于 2026-10-10，执行前应重新核对。

API 密钥只通过当前终端的环境变量读取：OpenAI 使用 `OPENAI_API_KEY`，DeepSeek 使用 `DEEPSEEK_API_KEY`，Anthropic 使用 `ANTHROPIC_API_KEY`。不要把密钥写进任务、配置或版本库。框架不自动读取 `.env`。

已在本地环境配置好相应密钥后，可先只运行两个廉价候选：

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

密钥缺失时会在发送请求前报错；没有自动重试网络请求。此版本的真实适配器已用协议样本测试，尚未完成供应商在线连通性试跑。

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
- 请求体限制为最多 64000 UTF-8 字节（默认 32000），避免进入当前候选的长上下文价格区间。发送前按请求字节数、协议余量和最大输出预留；这不是供应商认证的分词计数，因此美元／Token 预留不能保证精确的最高账单。
- 调用次数、工具步骤和修复次数由框架控制；运行时间在阶段切换时检查，并用于网络／检查超时。供应商端已在途的推理无法由本地框架保证取消。
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

检查程序是操作者提供的独立 Python 文件，从 `LAB_WORKSPACE` 读取本次代码副本。退出码 0 表示通过，1 表示任务失败，2 表示检查环境错误。检查文件必须位于 `source/` 外面。

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
$LabPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $LabPython -m unittest discover -s tests -v
```

适配器实现依据：

- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)：Responses 工具调用、工具结果与推理块延续。
- [DeepSeek tool calls](https://api-docs.deepseek.com/guides/tool_calls/) 和 [Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)：工具循环、思考内容及用量。
- [Claude tools](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools) 和 [Messages](https://platform.claude.com/docs/en/api/messages/create)：工具块、结果块与缓存用量。
