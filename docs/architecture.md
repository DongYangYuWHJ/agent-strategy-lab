# 第一版工程约定

## 目标与实验边界

模型初筛与单 Agent 实验使用同一套运行框架。第一版先完成单 Agent 的完整闭环：任务 → 独立源码副本 → 模型／工具循环 → 公共检查和有限修复 → 最终验收 → 用量与费用汇总。

三个演示任务用于验证流程，固定回放只证明框架工作，不证明任何模型有能力完成任务。正式筛选与正式架构比较应使用不同任务集，增加任务规模、难度与重复次数。

## 模块职责

| 模块 | 职责 |
|---|---|
| domain | 版本、任务、模型、价格、限制、计划、用量、工具调用 |
| accounting | 发送前预留、实际响应计量、费用估算、执行计数 |
| providers | 原生 API 请求／响应与工具协议适配 |
| settings | 环境变量优先、本地供应商密钥补充，独立于实验快照 |
| workspace | 原始副本、可编辑文件名单、受限文件操作、补丁 |
| tools | 所有模型共用的工具定义与调用校验 |
| evaluation | 操作者定义的公共／最终检查 |
| strategies | 验证之后的修复、结束或停止决策 |
| runner | 生命周期、模型循环、状态、公共督察和记录 |
| experiments | 冻结批次、固定随机顺序、总预算和续跑 |
| telemetry / reporting | 事件与状态记录、统计、报告 |
| opencode_bridge | 固定版本核对、角色加载诊断、进程级密钥注入与交互启动；尚未作为批次后端 |

## 公共约定（schema_version = 1）

Task：ID、描述、公共验收条件、源码起点、可编辑文件、公共检查及最终检查。模型只收到公共任务定义；操作者路径和最终检查内容不进入提示词。

Run：唯一 ID、任务和源码指纹、框架指纹、策略名／版本、角色模型参数、价格、限制、提示词、工具定义、状态、累计用量与时间。

Credential：环境变量或 settings.local.json 按供应商提供密钥。原生 runner 在供应商实例内存中用于鉴权头，不向检查子进程传递；OpenCode 桥接则只向 OpenCode 子进程注入所需供应商环境变量。密钥不是 Model 的字段，不写入 Run、批次身份、提示词或用量记录。settings.example.json 提供可共享的空模板，本地文件被 Git 忽略。密钥可轮换而不修改实验参数；配置状态检查不等同于在线认证或余额检查。

Plan：目标、步骤、相关文件、约束、未解决问题。已定义数据结构，尚未启用规划模型。

Evidence：具体工具请求／结果、检查退出码、日志、验证脚本指纹及发生时间。模型文字“通过”不会被当作验收证据。

Result：是否合格、运行状态、停止原因、修复次数、归一化用量、估算费用、未知费用预留、时间、交付物位置、最终验收记录。

Usage：输入包含缓存读取和写入；输出包含推理用量。额外字段仅用于拆解，不能再次计入总 Token。供应商用量缺失、不合法或尚未收到时终止并标记未知。

## 状态和停止原因

运行阶段：preparing、executing、waiting_for_model、model_response_recorded、public_verification、repair、final_acceptance、finished。

最终状态：succeeded、failed、stopped、error、cancelled；未保存最终结果的旧目录在报告中显示 interrupted。

停止原因独立记录，包括 accepted、acceptance_failed、repair_limit、no_progress、call_limit、tool_limit、token_limit、output_token_limit、generation_length_limit、request_size_limit、input_estimate_limit、incomplete_model_response、budget_limit、time_limit、check_timeout、usage_unknown、provider_error、malformed_model_response、environment_error、interrupted。旧报告中的 context_limit 是旧版本的本地请求字节拦截，不能解释为供应商上下文窗口耗尽。

批次完成表示实验单元已执行，不表示任务全部成功。任务失败照常计入汇总；用量未知时暂停剩余调用。

## 策略扩展

SingleAgent 策略只决定公共检查之后是否修复、结束或停止。协调器始终管理公共限制，策略不能重置账本。

Action.REPLAN 预留给“满足升级条件，请求规划者调整计划”的路径。下一版可以增加 PlannerWorker，并通过 Plan 传递信息。升级时继续使用原 Run ID、同一账本与全局上限，规划、交接、重试和审查成本全部记录。

第一版不启用多数投票督察。先记录工具错误、虚假完成声明、验证失败与循环，用这些证据判断是否值得加入语义审查。以后模型审查的输出应包括依据、问题位置、建议核验和“无法判断”，并测量误报、漏报和成本。

## 公平比较

同一任务使用相同初始代码、工具、可编辑范围与最终验收。保存工具和提示词快照；记录模型参数及价格版本。随机种子只控制运行顺序，不代表模型生成可复现。

任务清单支持显式 tasks 数组和 task_globs 文件扫描。扫描结果排序、按规范路径去重，再逐项验证；不同路径的重复任务 ID 会报错。发现的路径、内容指纹和任务／模型／重复次数组成的计划在批次启动时冻结。续跑重新核对，新增任务不会静默改变原批次。list-tasks 可预览清单或导出 JSON 数组，不触发模型调用。

公共检查可供执行者修复；最终验收不进入修复反馈。检查程序由操作者维护并复制到工作目录以外。不得让执行者自己修改评分标准。

检查层以 `check_host` 运行可信评分脚本，使用 `check_client` 将被测函数／程序放入独立进程，预期结果保留在 host。只有结果正确、评分正常完成、且本次完成记录一致才接受；退出码 0 不再单独表示通过。运行辅助代码的摘要在检查前后核对。进程分离没有提供 OS 沙箱或隐藏测试的文件系统保密保证。

LiveCodeBench 初始子集和专用单 Agent 配置位于 `benchmarks/livecodebench/` 与 `configs/livecodebench-single.json`。来源、难度、全部用例和操作者正负对照可追溯；这是本地 stdio 子集适配，不与官方排行榜分数混用。

模型目录可选匹配模型计数（`token_counting=model`）或旧字节估计（`estimate`）。匹配计数中，DeepSeek 使用固定版本的本地官方文本 tokenizer 和对话模板，OpenAI／Claude 使用官方计数接口；输入计数加配置余量及最大输出用于准入，真实统计仍使用生成响应报告的用量。计数失败为 `input_count_error`，不发送生成请求、不自动回退或重试，批次停止。计数调用单独记录，不计入生成调用次数，其时间计入整题时间。因分词、供应商变化、超时及计价差异，预算保护不等同于账单硬限制。实付费用应另行核对。

## 当前限制

- 原生批次仅单 Agent、串行、Python 独立检查程序；没有容器沙箱、任意命令执行、依赖安装和在途会话恢复。OpenCode 交互原型独立启动，尚未接入批次验收、预算和结果格式。
- 供应商适配器已用离线协议样本测试；2026-10-12 验证 deepseek-flash 和 gpt-6-luna，2026-10-13 验证 claude-haiku-5-5，三者均完成单任务工具循环与最终验收，用量完整。其他模型及供应商实付账单仍待核验。
- 深度推理设置跨供应商语义不同。DeepSeek 使用 thinking 开关与 reasoning_effort（none／low／high／max，默认候选配置为 low）；OpenAI 使用 reasoning.effort；Claude 使用 adaptive thinking 和 output_config.effort。相同标签不能直接理解为相同计算量。
- 模型别名可能在供应商侧更新；即使本地配置不变，也不能保证模型权重固定。
- 文件工具不能读取最终验收程序，但生成代码在检查进程中运行，目录隔离不提供对恶意代码的保密／隔离保证。引入不可信代码之前需要 OS 沙箱。
