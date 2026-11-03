# Windows 可运行的真实 Python 仓库任务

2026-11-02 另新增 [九个工程任务候选](task-calibration.md)，覆盖三个项目的专项和组合需求；与本文两项历史升级任务分别保存，尚未进行模型筛查。

采用真实项目的固定历史源码，在现有 Python 3.12 环境运行，不安装 Docker、Linux、pytest 或额外运行依赖。保留上游许可证、源码、说明及原测试文件；原 pytest 测试供模型阅读，本实验的可执行验收另用标准库编写，不能宣称已通过上游完整测试套件。

| 任务 | 原始库代码行数 | 可读文件数 | 可编辑包模块 | 公开／最终场景 |
|---|---:|---:|---:|---:|
| TinyDB：文档 ID、批量 API 与组合查询升级 | 1,866 | 42 | 10 | 5／30 |
| ItsDangerous：密钥轮换与时间验证升级 | 1,075 | 40 | 10 | 4／35 |

这是比原六个小型手工仓库更大的代码理解／兼容性任务，仍属于紧凑的库项目，不能等同于 SWE-bench Pro 的大型服务系统。行数为基准包的物理 Python 行数，含注释与空行；可读文件数包括文档和上游测试，不能当作代码模块数或难度指标。两题均为开发集，未测定难度，不能依据两题推断通用模型排名。

## 来源与验收边界

- TinyDB 基准为 `v4.0.0`，固定提交 `a01de8fee6a6c6b4174fcb0e54d6a5e656541e55`；参考基于 `v4.8.0`，提交 `429b27a513f0ad301632379e55667dd99865fb16`。
- ItsDangerous 基准为 `1.1.0`，提交 `6e6359864be6055860adf1e11d8bb0db69ff1840`；参考为 `2.2.0`，提交 `096c8d42545d3b68ea21a4f890fb2b2d8979c0bd`。
- **真实源码＋人工整理的升级需求和验收**，不是原始 GitHub issue，也不是第三方标准基准。参考版本号、参考代码和隐藏场景只在操作者目录，不交给模型。模型可读完整基准包及说明，全部包模块可编辑，不按参考补丁定位文件。
- TinyDB 的独立测试发现参考上游版本对混合显式／自动 ID 批次不能满足本任务的统一 ID 约定。参考实现额外修复 `insert_multiple` 的分配、重复检查及下一 ID 缓存；这属于本实验自定合同，不能声称原样上游版本通过。
- TinyDB 验收覆盖 ID、批量读取、upsert、组合查询、可变映射缓存，以及内存／文件／缓存中间件三种存储。ItsDangerous 验收覆盖四类序列化器、直接签名、旧密钥验证、最新密钥签发、摘要回退、salt 隔离、篡改拒绝、时效边界和 UTC 时间。覆盖有限，不是穷尽正确性或生产安全审计。
- `source/app.py` 是不可编辑的输入适配器，直接调用项目包，不承载参考解法。库必须实现公开 API，避免只在适配器中重写业务功能。最终验收含公开场景；隐藏场景只在最后执行，不用于追加修复提示。
- 真实库使用了长文件，运行器新增 `read_file_chunk` 与唯一文本 `edit_file`，让模型能完整阅读和局部修改；原白名单、规划轮禁写、角色权限与验收隔离依然生效。工具集合改变，不能把新旧批次费用差异全归因于题目规模。

## 准备与实验配置

[固定下载来源](../scripts/python_repo_fixtures/sources.json)、[生成器](../scripts/build_python_repo_tasks.py)、[任务清单](../benchmarks/pure-python-repos-v1/manifest.json)、[当前付费测试配置](../configs/workflow-python-repo-cost-guarded.json)。下载包校验和固定，构建拒绝覆盖已有任务集。

```powershell
.\.venv\Scripts\python.exe scripts/build_python_repo_tasks.py --download
```

保留同一四轮日常对话，允许实现时自查和返工，Luna／DeepSeek 单体各做两题，每格一次。**按用户确认，仅保留整批 $2 预算，其他本地执行额度取消**。完全无限额配置保存在 [comparison 配置](../configs/workflow-python-repo-comparison.json)，此前启动被自动审批拒绝、未发出模型请求；用户随后同意使用 cost-guarded 配置。原首轮的有限额参数另存为 [bounded 配置](../configs/workflow-python-repo-bounded.json)，对应下方的首轮结果。配置变更后必须使用新的输出目录，不能续跑或改写旧批次。

```powershell
.\run-lab.cmd batch --experiment configs/workflow-python-repo-cost-guarded.json --output artifacts/python-repo-comparison-cost-guarded-live-01
```

尚未执行的线上批次不能称为结果。任务／工具验收通过后才启动；失败保存原始轨迹，不自动调参或重跑。

## 临时取消本地额度：2026-11-01

实验配置中的 `limits` 用 JSON `null` 明确表达不设上限，而不是用很大的数字代替。API 调用、工具步骤、累计 Token、单次输入估计、请求字节数、总运行时间、模型请求超时、计数超时、验收超时、费用及整批预算均设为 `null`；修复／无进展计数上限也关闭。四轮任务流程本身不变。

模型配置使用独立的 [models-python-repo-unlimited.json](../configs/models-python-repo-unlimited.json)，仅包含 Luna 和 DeepSeek：两者 `max_output_tokens=null`、`enforce_total_token_limit=false`；网关会移除 OpenCode 补入的输出长度字段。Luna 保持 medium、DeepSeek 保持 low。原来供其他实验使用的 model catalog 不改。实验 JSON 的 `catalog` 指定该文件，CLI 自动读取；显式 `--catalog` 会覆盖它，重测时不要带旧 catalog 参数。

计量、调用轨迹、逐轮快照、权限和隐藏验收继续生效。用量缺失或接口故障仍作为异常停止，不能因为取消额度就执行未计量的工具或自动重试付费生成。模型的上下文、最大输出、速率和账户余额限制由供应商控制；OpenCode 中的 context/output 是服务能力元数据，不是伪造的无限值。

Luna 超过 272,000 输入 Token 的完整请求采用长上下文费率：输入／缓存读／缓存写为短上下文的两倍，输出为 1.5 倍。实际用量决定计价档位，不按本地估计数给账单定价。来源：[Luna 官方模型说明](https://developers.openai.com/api/docs/models/gpt-6-luna)、[标准价格](https://developers.openai.com/api/docs/pricing)。DeepSeek 延续峰值价格估算，不自动按时段折算，因此仍不能当作账户账单。

**保留的技术边界**：OpenCode 2.0.32 的 MCP 超时只接受正整数，无法传入无限值；移除实验设置后，单次工具执行仍采用引擎默认 12 小时。模型 HTTP 的总超时、默认 5 分钟响应头和 15 分钟流间隔超时已通过 `timeout/headerTimeout/chunkTimeout=false` 关闭。本地服务启动、目录权限、文件工具分块／内容大小及协议完整性检查继续保留，不属于生成额度。来源：[OpenCode MCP 超时](https://opencode.ai/v2/docs/mcp-servers/#timeouts)、[模型连接超时](https://opencode.ai/v2/docs/providers/#timeouts)。

变更验证：[155 项回归检查](../artifacts/unlimited-regression-20261101-01.log)通过；补充超时设置后的 [7 项针对性检查](../artifacts/unlimited-targeted-20261101-02.log)通过；[本机固定回复流程](../artifacts/unlimited-protocol-20261101-03/report.json)执行 40 次模型步骤并完成四轮验收，超过旧调用上限，零付费生成。完全无限额配置未用于真实付费生成；仅保留 $2 预算的配置已完成下面的四项测试。

## 两题是否足够

两题适合先验证更大仓库的完整交付、计量与验收路径，不足以支持模型总体排名、架构省钱结论或稳定通过率。两题来自两个紧凑库项目，均为人工整理的升级合同；此前限额批次未完成，本轮两模型均完成。后续逐步覆盖配置接线、存储一致性、接口兼容、批量操作、权限与回归等不同任务，并对关键对照重复。可将跨 3–5 个项目的约 10–20 项任务作为下一阶段工作规模；这是实践目标，不是统计充分性的保证。

## 保留整批 $2 后的线上测试：2026-11-01

每格一次，无调参、无付费重跑。四项均完成四轮对话并通过最终验收，用量完整，总估算 **$0.187572820**，未触及预算。最终验收包含公开场景；模型在四轮结束前没有接收隐藏反馈。

| 任务 | 模型 | 最终验收 | 生成调用 | 累计 Token | 估算费用 USD | 秒 |
|---|---|---|---:|---:|---:|---:|
| TinyDB | DeepSeek | 30/30 | 38 | 2,034,752 | 0.096527196 | 399.516 |
| TinyDB | Luna | 30/30 | 39 | 1,405,338 | 0.030233200 | 243.844 |
| ItsDangerous | DeepSeek | 35/35 | 26 | 706,672 | 0.047404284 | 198.234 |
| ItsDangerous | Luna | 35/35 | 25 | 493,251 | 0.013408140 | 143.750 |

- 两题合计：DeepSeek $0.143931480／597.750 秒；Luna $0.043641340／387.594 秒。按本实验冻结计价，Luna 估算费用低约 69.7%；DeepSeek 使用峰值价格，未按时段折算，不能把这个比例当作实际账单节省比例。
- 两模型都用了 64 次生成调用，费用仍有明显差异。调用次数不能单独代替输入／输出用量、缓存和单价；本轮质量只按所定义的行为验收评价。
- 本轮 TinyDB 的 DeepSeek 轨迹单次输入估计峰值为 103,605，生成 38 次，确实超过旧 64,000 输入／30 次调用边界。两项 Luna 的累计 Token 也超过旧 200,000。本轮得到完整交付记录，但因每格一次且生成有变化，不把全部差异归因于单一参数调整。
- 当前两题仍没有区分最终通过与否，只观察到这些模型配置下的成本、耗时和用量差异。不能据此推断模型总体能力相同，或某种多 Agent 架构一定省钱。

证据：[比较报告](../artifacts/python-repo-comparison-cost-guarded-live-01/comparison.md)、[机器汇总](../artifacts/python-repo-comparison-cost-guarded-live-01/comparison.json)、[冻结批次配置](../artifacts/python-repo-comparison-cost-guarded-live-01/batch.json)。原有限额批次保留，结果不混合计算通过率。

## 本机离线验证

最终审计：[8 组对照全部通过](../artifacts/pure-python-repos-audit-20261101-03/audit.json)。每题检查原版本失败、参考实现通过、仅覆盖公开场景的部分修复在最终验收失败，以及提前退出不能伪造通过。此前失败的审计记录保留，验收驱动中的临时目录访问、Base64 篡改样例及参考实现的混合 ID 边界均在付费生成前修正。

[148 项运行器回归](../artifacts/pure-python-regression-20261101.log)通过；[本机 OpenCode 固定回复流程检查](../artifacts/pure-python-tools-protocol-20261101-02/report.json)完成四轮并验收通过。固定回复证明工具和权限接入，不作为模型能力数据。

## 首轮线上结果：2026-11-01

四项均按冻结参数各执行一次，未调参或重跑，用量完整，总估算费用 **$0.085419013**。四项均仅完成规划轮，在实施轮停止，没有执行模型侧公开检查，也没有进入最终验收。

| 任务 | 模型 | 停止的具体原因 | 成功写入操作 | 估算费用 USD |
|---|---|---|---:|---:|
| TinyDB | DeepSeek | 单次输入门限 64,000 | 0 | 0.041728608 |
| TinyDB | Luna | 累计 Token 放行／预留门限 200,000 | 4 | 0.006825220 |
| ItsDangerous | DeepSeek | API 调用上限 30 | 18 | 0.030448140 |
| ItsDangerous | Luna | 累计 Token 放行／预留门限 200,000 | 5 | 0.006417045 |

写入操作含局部修改，不等于修改的文件数。两个 DeepSeek 记录外层 stop_reason 为 `opencode_session_error`，原始网关事件明确记录 `input_estimate_limit`／`call_limit`，不能误记为不明网络或环境故障。Luna 在下一次请求预留输入及最多 16,384 输出时触及门限，实际累计用量分别为 169,562／173,575，未扣费的拒绝请求不算作实际生成。

这轮证明 Windows 原生任务接入和计量可运行，但现有资源策略限制了端到端评估。**不能把四项统计成完成实现后的验收失败，不能用这些未完成支出比较成功解决任务的成本。** 两模型的累计 Token 策略本来就不同；预算与上下文策略应在后续新批次明确调整、重新冻结，再讨论完成质量。当前未自动追加新批次。

证据：[比较报告](../artifacts/python-repo-comparison-live-20261101-01/comparison.md)、[逐项机器数据](../artifacts/python-repo-comparison-live-20261101-01/comparison.json)。
