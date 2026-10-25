# 010：通用 prompt 工作流

记录日期：2026-10-24。目的已补入 [009](009-single-agent-summary-and-parameter-failures.md)；本篇只保留功能说明，不作为新的研究方向。

为模拟日常使用，在同一任务和会话中固定四轮交互：提出任务与方案 → 复核方案并实施 → 核对需求 → 核对测试和交付声明。各架构接受相同外部消息，比较最终交付、整段费用和耗时，不研究哪句 prompt 更有效。

工作流与任务、模型架构分开配置，复用现有调参题，不以创建 CSV 等业务场景为前提。OpenCode 处理模型和内部工具循环，实验程序调度消息、限制文件范围、统一计量和停止，全部回合结束后独立验收。

入口：[工作流说明](../workflow-experiments.md)、[四轮配置](../../configs/workflows/daily-review.json)、[实验配置](../../configs/workflow-single.json)。证据以 artifacts 中的冻结配置、请求响应、轮次记录和报告为准。用户授权一次线上流程检查，出问题保留结果，不自动修改后重跑。

## 已完成验证：2026-10-24

先完成 DeepSeek 单次接入检查，随后五模型各在同一道 Happy New Year 2025 上运行一次。五者均完成四轮，公开 4/4、隐藏 40/40 通过，用量完整，未调参重跑。比较批次的任务、工作流、运行器和限制一致，输出上限均为 16k；每模型预算 $0.50，整批 $2.50。

| 模型 | 本轮估算费用 USD |
|---|---:|
| Luna | 0.001074930 |
| Haiku | 0.002829110 |
| DeepSeek Flash | 0.003949092 |
| Sol | 0.015136300 |
| Sonnet | 0.040408400 |

五模型批次合计 **131689 Token、$0.063397832**，不包含此前单独的 DeepSeek 接入检查。费用按供应商 usage 与冻结价格估算；DeepSeek 使用保守高峰价，缓存条件也影响费用。DeepSeek 推理档位为 low，其余为 medium，跨供应商档位不保证等价。

结论：四轮工作流已验证可在三家供应商的五种单 Agent 模型上执行、验收和计量；一道简单题各一次的费用次序不作为稳定排名。Planner＋Executor 的真实协作仍待验证，保留评估集未使用。

证据：[费用与分轮比较](../../artifacts/workflow-model-comparison-20261024-01/cost-comparison.md)、[精确数据](../../artifacts/workflow-model-comparison-20261024-01/cost-comparison.json)。复用入口：[五模型实验配置](../../configs/workflow-model-comparison.json)、[本轮冻结模型价格目录](../../configs/models-workflow-comparison.json)。
