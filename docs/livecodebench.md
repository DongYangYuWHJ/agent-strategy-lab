# LiveCodeBench 单 Agent 任务与验收

第一版保留六道真实任务；扩充版现有 18 道，easy、medium、hard 各六道。它们用于检查输入、代码产物、公开反馈与最终验收，并探索单模型参数；数量与来源分布尚不足以用于整体模型能力排名或架构结论。扩充工作没有调用任何付费模型。

## 扩充版：校准、调参与保留评估

扩充版单独保存在 `benchmarks/livecodebench-v2/`，不改动原六题、原配置或已经生成的实验结果。来源仍是同一官方固定 revision 的 `test6.jsonl`；新增十二题覆盖 2025 年 1—3 月的多个 AtCoder 比赛。当前只适配 Python stdio 题，不能视作对全部平台、函数接口或工程任务的代表性覆盖。

| 用途 | easy | medium | hard | 合计 |
|---|---|---|---|---|
| calibration：已有六题 | 2 | 2 | 2 | 6 |
| development：新增调参题 | 2 | 2 | 2 | 6 |
| holdout：新增保留评估题 | 2 | 2 | 2 | 6 |
| 总计 | 6 | 6 | 6 | 18 |

共保留 51 个公开用例、720 个隐藏用例，不删减原测试。官方 difficulty 不变；manifest 另有操作者标注的 topic，用于描述网格、栈、事件查询、树形动态规划、位置优化、图搜索和最短路径等类型，不是额外的官方难度等级。保留集的输入输出接线和验收校准不涉及模型；不要用其模型成绩反复调参。

- `configs/livecodebench-development.json`：已有六题＋新增六道调参题，共 12 题，各难度四题；只包含 DeepSeek 和 Luna，可用 `--models` 单选。
- `configs/livecodebench-additional-models.json`：同样的 12 题，候选为 Sol、Claude Sonnet、Claude Haiku，每模型每题一次；尚未启动此批线上实验。
- `configs/livecodebench-holdout.json`：六道保留题，各难度两题，与调参配置完全不重叠。
- `benchmarks/livecodebench-v2/manifest.json`：逐题来源、原难度、split、topic、用例数及原始记录摘要。
- `benchmarks/livecodebench-v2/exclusions.json`：已发现的不合格候选题与剔除原因。

候选 `abc392_f / Insert` 的第 15 个隐藏输入违反题面 `1 <= P_i <= i`：第一步出现 `P_1=3`。本次整题剔除，没有修改预期答案或删除个别用例，改用同为官方 hard 的 `abc393_d / Swap to Gather`。首次失败审计保存在本地 artifacts 中。最终 18 题已完整通过正负对照审计：36 项正对照检查通过、108 项负对照检查被拒绝，记录为 `artifacts/lcb-v2-audit-20261021-02/audit.json`；88 项离线回归测试通过。

以下命令不调用模型：

```powershell
.\run-lab.cmd validate --experiment configs/livecodebench-development.json
.\run-lab.cmd list-tasks --experiment configs/livecodebench-development.json
.\run-lab.cmd audit-livecodebench --suite-root benchmarks/livecodebench-v2
```

`audit-livecodebench` 也支持 `--split calibration`、`--split development` 或 `--split holdout`。重新获取到新目录时，使用 `import-livecodebench --suite expanded --output <新目录>`；它按固定 ID 流式扫描，最多读取 64 MB，单条记录最多 16 MB。

准备好参数后，可以手动运行下面的真实 API 实验。本次扩充没有执行这些命令：

```powershell
.\run-lab.cmd batch --experiment configs/livecodebench-development.json --models deepseek-flash --output artifacts/lcb-dev-deepseek-01
.\run-lab.cmd batch --experiment configs/livecodebench-development.json --models gpt-6-luna --output artifacts/lcb-dev-luna-01
```

## 调整 Token 和运行限制

这些设置作用于原生 `run-lab.cmd batch`，不会自动修改 OpenCode 交互终端的模型参数。2026-10-21 后续调整：DeepSeek、Luna 的单次输出提高至 16384，并分开请求体传输大小与输入 Token 估计；详见 [008：续接与额度修复](decisions/008-continuation-and-limit-fix.md)。

| 参数 | 修改位置 | 含义 |
|---|---|---|
| `max_output_tokens` | `configs/models.json` 中各模型条目 | 单次模型请求的最大输出；目前 DeepSeek、Luna、Sol、Sonnet、Haiku 都是 16384，Astra、Fable 暂保留原设置。推理也可能消耗这部分额度 |
| `reasoning_effort` | 同上 | 模型推理档位；跨供应商不保证同名档位等价 |
| `token_counting` | 同上 | 当前为 `model`：匹配模型计数；`estimate` 为明确选择旧估计方式 |
| `limits.max_total_tokens` | 所运行的实验 JSON | 一道任务所有请求的输入＋输出累计上限，目前 100000 |
| `limits.max_request_bytes` | 同上 | 单次请求 JSON 的 UTF-8 传输字节上限，目前 1048576（1 MiB），也是程序允许的最大值；不是模型的 Token 上下文窗口 |
| `limits.max_estimated_input_tokens` | 同上 | 单次输入的保守 Token 估计上限，目前 64000；用于费用和累计 Token 准入，不能代替供应商分词计数 |
| `limits.request_timeout_seconds` | 同上 | 单次 API 请求等待上限，目前 300 秒（5 分钟）；整题剩余时间不足时以剩余时间为准 |
| `limits.token_count_timeout_seconds` | 同上 | 官方计数接口的等待上限，默认 30 秒；与生成请求等待时间分开 |
| `limits.token_count_margin` | 同上 | 在匹配计数上额外预留的输入 Token，默认 256；不是实际消耗 |
| `limits.max_cost_usd` | 同上 | 单道任务的费用准入预算，目前 0.20 美元 |
| `batch_budget_usd` | 同上 | 整批累计费用准入预算，目前 1 美元 |

例如，要试验 8192 的单次输出额度，应修改 DeepSeek 与 Luna 各自条目的 `max_output_tokens`，而不是只提高整题累计 Token。扩大输出额度会提高发送前费用／Token 预留；批次可能因预算不足而提前停止，报告会记录原因。供应商明确报告输出额度用尽时，现记录 `output_token_limit` 并保留费用；不再把截断空回复当成提交，不执行截断响应中的工具，也不自动重试。

Luna 上轮约 37 KB 的后续请求是被旧版 32000 字节保护拦下的。现在传输层允许 1 MiB；发送和保存的续接内容保持完整。2026-10-23 起，真实模型目录启用匹配模型的输入计数：DeepSeek 使用本地固定版本的官方 V4.1 分词文件和对话模板，包含工具定义、调用结果及完整推理历史；OpenAI／Claude 分别使用官方计数接口。输入预留为计数结果加 256 Token 余量，不再直接把请求字节数当作 Token。API 计数端点失败时停止为 `input_count_error`，不发送生成请求，也不自动回退或重试；本地 DeepSeek 计数不额外联网。

旧的估计方式仍可通过模型条目的 `token_counting: "estimate"` 显式选择。无论哪种方式，最终用量和费用都取生成响应的 usage。计数、余量、接口方法与本地 tokenizer 的版本／摘要均可追溯；实际计数不等同于精确账单上界。

传输包过大停止为 `request_size_limit`；估计输入超过 64000 停止为 `input_estimate_limit`；整题累计 Token、预算、时间、调用次数等继续分别限制。每次准备请求的传输字节与输入估计都会写入事件记录，即使随后在发送前被拦截。提高输出上限可能使下一轮的代码、工具调用或续接内容变大，因此两个限制有间接关联，没有固定换算比例。

更改模型目录会影响之后引用它的所有原生实验。调整任务或参数后使用新的输出目录，旧批次的 `--resume` 会核对并拒绝配置变化。先用 `validate --experiment ...` 检查配置；它不会调用模型。

## DeepSeek 参数复查：匹配计数与 32k 输出

`configs/deepseek-parameter-check.json` 只选上轮受额度影响的两道困难题：Dangerous Sugoroku 和 Hierarchical Majority Vote，只运行 DeepSeek，每题一次。累计 Token 仍为 100000，单次生成等待仍为 300 秒，单题／整批金额预算仍为 0.20／1 美元，推理档位仍为 low；本次没有更改提示词或自动缩减输出额度。

先用匹配计数和原 16k 输出，检查预留修正本身的影响：

```powershell
.\run-lab.cmd batch --experiment configs/deepseek-parameter-check.json --output artifacts/deepseek-counted-16k-01
```

再使用同一任务配置和专用模型目录，仅把 DeepSeek 单次输出提高到 32768：

```powershell
.\run-lab.cmd batch --experiment configs/deepseek-parameter-check.json --catalog configs/models-deepseek-32k.json --output artifacts/deepseek-counted-32k-01
```

这两条都会产生真实模型费用，本次准备工作没有执行。每条各运行两项，不会包含 Luna 或其他模型。第二条读取 `configs/models-deepseek-32k.json` 中的 `max_output_tokens`；第一条读取 `configs/models.json`，其中 DeepSeek 仍保留 16384。程序当前允许单次输出最大为 32768。输出目录如果已存在，应换一个新的后缀，不自动覆盖或续跑旧实验。

建议此次只比较计数方式与 16k／32k，先保留累计额度、时间、推理档位、提示词和任务。后续若再次触发其他门槛，先查看停止原因再讨论调整。开发配置中的 `token_count_margin=256` 为计数余量，暂不依据一次成功就减小。保留评估集仍不参与这项复查。

分词资产来源和版本见 [资产说明](../assets/tokenizers/deepseek-v41/README.md)。OpenAI 和 Claude 的方法分别依据 [OpenAI 官方计数说明](https://developers.openai.com/api/docs/guides/token-counting)、[Claude 官方计数说明](https://platform.claude.com/docs/en/build-with-claude/token-counting)。仅本地计数和模拟测试已验证；OpenAI／Claude 新计数端点的本账户权限和实际网络调用尚未验证。

离线核对上轮 DeepSeek 的 54 次保存请求，本地计数均与对应响应的输入 usage 相同。重建此前被拦截的第 6 次请求，输入计数为 15646，替代旧估计 53268；加 256 余量后，16k／32k 的累计准入计算分别为 67702／84086，均低于 100000。这只是旧请求的计数与准入重算，不是新的解题结果。[离线核对记录](../artifacts/token-counting-audit-20261023/audit.json)

## 新增候选模型批次

新增配置沿用 DeepSeek／Luna 的调参任务、输出额度 16384、单次请求等待 300 秒、整题 900 秒及累计 100000 Token。三个新候选的推理档位均设为 medium；Luna 也是 medium，DeepSeek 仍保留 low，各供应商档位含义不同。Sol、Sonnet、Haiku 已有原生接口适配；Haiku 曾通过单个小任务的联网检查，不代表已完成本任务集评估，Sol／Sonnet 的本账户调用权限仍待线上确认。

该批单题金额准入预算为 **1 美元**，整批为 **5 美元**；原 DeepSeek／Luna 调参批仍保留单题 0.20、整批 1 美元。提高金额预算是为了容纳较贵模型的最大输出预留，不是预期花费，也不是供应商账单硬上限。两批金额限制不同，分析时应单独标出，不能称为相同美元预算比较。仍可能遇到累计 Token 等其他门槛，按实际停止原因记录，不自动调参重跑。

```powershell
.\run-lab.cmd validate --experiment configs/livecodebench-additional-models.json
```

下面是后续可手动启动的付费实验命令，目前没有执行。省略 `--models` 会运行三个新候选共 36 项；如只想测一个，追加 `--models gpt-6.1-sol`、`--models claude-sonnet-5-5` 或 `--models claude-haiku-5-5`。

```powershell
.\run-lab.cmd batch --experiment configs/livecodebench-additional-models.json --output artifacts/lcb-additional-16k-300s-01
```

型号、输出额度支持与价格核对：[Sol 官方模型说明](https://developers.openai.com/api/docs/models/gpt-6.1-sol)、[Sonnet 官方模型说明](https://platform.claude.com/docs/en/models/sonnet-5-5/overview)、[Haiku 官方模型说明](https://platform.claude.com/docs/en/models/haiku-5-5/overview)、[Claude 官方价格](https://platform.claude.com/docs/en/about-claude/pricing)。本次仅准备配置并检查加载，没有使用保留评估集或生成新模型成绩。

## 数据与接口

来源：[官方 Hugging Face 数据集](https://huggingface.co/datasets/livecodebench/code_generation_lite)，固定 revision `0fe84c3912ea0c4d4a78037083943e8f0c4dd505`，选取 `test6.jsonl` 中的六个固定 ID。该文件属于 release_v6 的增量；本批题目来自 2025 年 1 月的 AtCoder，不能称为最新题或保证模型从未见过。

| 任务 ID | 原标题 | 原难度 | 公开用例 | 隐藏用例 |
|---|---|---|---|---|
| lcb-abc387-b | 9x9 Sum | easy | 3 | 40 |
| lcb-abc387-a | Happy New Year 2025 | easy | 4 | 40 |
| lcb-abc387-c | Snake Numbers | medium | 3 | 40 |
| lcb-abc389-d | Squares in Circle | medium | 3 | 40 |
| lcb-abc387-f | Count Arrays | hard | 3 | 40 |
| lcb-abc388-f | Dangerous Sugoroku | hard | 3 | 40 |

所有题目保留完整原文、全部公开与隐藏用例；没有裁剪大输入、改写预期答案或给 Agent 提供参考实现。Agent 只需修改各自源码副本中的 `solution.py`，使用 Python 标准库，从 stdin 读取并向 stdout 输出。每个用例启动新进程。

目录为 `benchmarks/livecodebench/`：

- `manifest.json`：来源版本、任务 ID、难度、用例数与原始记录摘要。
- `upstream/`：仅六条选中记录，包含隐藏测试，供操作者追溯；不应喂给 Agent。
- `tasks/<id>/task.json` 与 `source/solution.py`：任务定义和未实现的初始文件。
- `tasks/<id>/public_check.py`、`final_check.py`：公开与隐藏评分程序，位于源码副本之外。
- `operator_controls/`：操作者编写的正对照实现，供检查适配器，不是上游官方 gold solution，也不能交给实验 Agent。

任务已随项目准备好，无需再次联网下载。`import-livecodebench` 可向一个新的输出目录重建相同任务集；它只流式扫描到所需记录，最多读取 32 MB，不拉取完整题库。隐藏测试的旧压缩格式通过禁止加载类／全局对象的受限反序列化器读取，不执行上游加载脚本。

## 查看与离线检查

```powershell
.\run-lab.cmd validate --experiment configs/livecodebench-single.json
.\run-lab.cmd list-tasks --experiment configs/livecodebench-single.json --json
.\run-lab.cmd audit-livecodebench
```

这些命令不调用模型。第三条对每道题运行四种操作者对照：正确实现、未实现的起始文件、只输出第一个样例答案的程序、提前退出的程序。正确实现应通过全部 19 个公开与 240 个隐藏用例；其他对照必须在公开和最终检查中被拒绝。记录写入新建的 `artifacts/lcb-audit-*/audit.json`，包含逐项证据与任务／对照代码指纹。

## 后续单 Agent 实验入口

`configs/livecodebench-single.json` 选择这六个任务，候选为 DeepSeek Flash、OpenAI Luna；可通过 `--models` 只选其一。每模型每题一次，沿用已有原生 runner 的记录和预算。整批费用准入预算 1 美元、单次 0.20 美元；它们不是供应商账单硬限制。每题运行上限 900 秒、一次检查 300 秒，每个被测进程最多约 6 秒。

下面的命令会产生真实 API 消耗，本次工作没有执行：

```powershell
.\run-lab.cmd batch --experiment configs/livecodebench-single.json --models deepseek-flash --output artifacts/lcb-deepseek-01
```

这是原生单 Agent runner 的入口。OpenCode 当前仍只有交互启动与角色加载，没有接入受控任务分发和独立验收，不能把上述结果标成 OpenCode 的实验结果。

## 本次验收修复

原问题是把检查进程的退出码 0 当作通过，导致被测模块在加载时调用 `os._exit(0)` 就可能跳过断言。

现在由外部受信任的 host 执行检查：函数任务通过 RPC 调用另一个进程中的被测代码；本批 stdin 任务直接在另一个进程执行 `solution.py`，由 host 比较实际 stdout 与预期结果。预期答案不放进被测进程的参数或环境。函数任务每次调用也重置进程，并把可变参数的修改传回检查端。

检查 host 只有在评分程序完成后才产生与本次调用绑定的完成记录。通过必须同时满足正确结果、检查正常完成及记录一致；日志里的成功字符串不参与评分。检查脚本和运行辅助代码在执行前后核对摘要；最终验收结果仍不反馈给 Agent 修复。

stdout 比较采用逐行去除首尾空白、字符串相等或精确 Decimal 数值相等的规则，避免大整数被浮点容差误判。保留标准 stdin/stdout 的 buffer API；正常打印后 `sys.exit(0)` 可通过外部结果比较，单纯提前退出不会因此通过。

这是适配所选 stdio 任务的本地评分器，不是完整的官方 LiveCodeBench harness：它没有覆盖函数式题目、其他语言、官方全部执行规则或排行榜条件，结果不能直接宣称为官方 benchmark 分数。

仍未实现 OS／容器安全沙箱。子进程不会继承 API 密钥，但仍拥有宿主用户的文件与进程权限；受信任控制样本的通过不证明可以防御主动恶意代码。内存、网络、文件系统隔离和整个进程树的资源限制仍需专门实现。本次修复针对提前退出导致的误判和评分进程完整性，不宣称验证层已经全面完备。
