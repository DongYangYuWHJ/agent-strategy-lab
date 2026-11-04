# 纯 Python 工程任务候选集：python-calibration-v1

2026-11-02 新增。使用当前 Windows 与现有 Python 环境；不安装 pip 包、Docker、Linux、数据库或其他服务。源码已随任务保存，执行任务不需要联网。

## 新增内容

在三个真实项目的固定源码上设计 **6 个专项任务与 3 个组合任务**。它们是本实验人工整理的新功能合同，不是原始上游 issue，也不是直接导入的官方 benchmark。

| 项目 | 任务 | 公开／最终场景 |
|---|---|---:|
| TinyDB | 跨表事务、嵌套保存点、缓存和 ID 回滚 | 3／26 |
| TinyDB | 快照恢复、冲突策略、无副作用预检 | 4／63 |
| TinyDB | 组合：事务中的快照恢复与回滚 | 7／98 |
| ItsDangerous | 用途绑定、激活时间、过期与容差策略 | 3／108 |
| ItsDangerous | 密钥／摘要／格式迁移，保留原签名时间 | 3／57 |
| ItsDangerous | 组合：迁移后仍遵守原用途与过期策略 | 6／177 |
| Cachetools | 动态调整容量，保持权重与淘汰规则 | 3／40 |
| Cachetools | 批量更新失败后恢复数据与缓存元数据 | 3／34 |
| Cachetools | 组合：调整容量后进行原子批量更新 | 6／79 |

最终验收含公开场景。合计 682 个执行场景，其中包含不同存储后端、序列化器、输入边界及组合任务的重复覆盖，**不是 682 道独立题**。三个组合任务复用了专项合同；同一项目的任务具有相关性，不能将九项当作九个独立项目样本。不得把同项目专项题用于调参，再把其组合题称为独立留出集。

任务重点是失败后状态是否完整、多个 API 是否共享一致状态、兼容旧行为以及组合约束；不强制修改指定数量的文件，也不以源码行数判定难度。当前三个基准包分别约 2,172、1,199、1,018 行 Python（含空行与注释），仍是紧凑库项目。首轮已观察到质量差异，见下方结果；稳定通过率及难度分层仍未测定，不能仅因需求变多就认定任务更难。

## 来源与文件

- [任务总清单](../benchmarks/python-calibration-v1/manifest.json)：列出任务、项目、版本、分组和场景数量。
- [固定源码与校验和](../scripts/calibration_fixtures/sources.json)：TinyDB v4.8.0、ItsDangerous 2.2.0、Cachetools v5.3.3；保留各自上游许可证。
- [任务生成器](../scripts/build_calibration_tasks.py)：从固定下载包重建，拒绝覆盖已有目录。
- [合同定义](../scripts/calibration_fixtures/tasks.py)、[独立编写的场景期望](../scripts/calibration_fixtures/cases.py)：维护需求和验收的源文件；参考实现没有用于动态生成期望值。
- [实验配置](../configs/workflow-python-calibration.json)：自动发现九个 task.json，沿用四轮 OpenCode 单体流程。DeepSeek／Luna 各一次，共 18 项；首轮已完成。

每题包含 source/（真实项目源码、只读适配器、需求和公开测试）、外部 public_check.py/final_check.py，以及 operator/ 下的参考补丁和错误对照。运行器只复制 source/ 给 Agent，隐藏验收和参考解法不提供给模型。整个项目包的现有 Python 模块均可编辑，不按参考补丁限定修改位置。

原有算法、六个小仓库及两项升级任务保持独立；不覆盖历史任务或实验结果。

## 验收与审计

每题检查起始代码失败、参考实现全部通过、故意错误的实现通过公开检查但被隐藏检查拒绝，以及提前退出不能伪造通过。组合任务分别使用两种错误实现，总共 39 组对照。错误类型包括回滚后 ID 缓存过时、忽略恢复冲突、过期边界差一、迁移刷新时间戳、缩容只淘汰一次、批量更新浅复制导致回滚不完整。

验收由独立宿主比较实际返回值和预先写定的期望，不相信提交程序自己的通过声明。新任务通过 run_many 一次隔离调用执行多个场景，每个场景创建独立库实例；不会逐场景启动 Python。外部宿主仍逐项评分并要求完整响应和验收回执。此变化仅适用于新任务的适配器与验收，不改旧任务协议或运行器核心。

验收日志中的 `LAB_GROUP_RESULTS` 分别记录回归、事务回滚、冲突、过期、签名、容量等需求组的通过数；最终全通过判定继续保留。现有主报告结构未变，分组数据目前在验收日志中，不自动将场景数量作为需求权重。

最终审计证据：[39 组对照](../artifacts/python-calibration-audit-20261102-04/audit.json)。先前检查记录保留：第一轮受到逐场景进程启动开销影响；第二轮发现验收把 BadTimeSignature 子类与 BadSignature 父类过严区分，现按异常族比较，并保留独立的 SignatureExpired 分类；第三轮通过，之后补充跨格式迁移、预检 ID 无副作用与权重计算失败等场景，再执行最终审计。未调用付费模型。

审计是有限正负对照，不代表穷尽正确性，不等同于上游完整 pytest 测试通过或密码学安全审计。上游测试文件供阅读，本任务执行验收使用 Python 标准库与附带包源码。

## 查看与复现

只校验配置、查看任务，不调用模型：

```powershell
.\run-lab.cmd validate --experiment configs/workflow-python-calibration.json
.\run-lab.cmd list-tasks --experiment configs/workflow-python-calibration.json
```

在新的目录重建任务并运行本机离线审计：

```powershell
.\.venv\Scripts\python.exe scripts/build_calibration_tasks.py --output artifacts/calibration-rebuild --download
.\.venv\Scripts\python.exe scripts/audit_repo_tasks.py --suite artifacts/calibration-rebuild --output artifacts/calibration-rebuild-audit
```

下载只在缺少固定源码包时需要网络，不安装软件。当前机器上的源码和缓存均已准备好。若系统临时目录不可写，可将当前终端的 TEMP/TMP 指向项目内可写临时目录；本次检查已在当前权限下完成，不修改全局环境变量。

配置沿用已有两个模型 catalog、本地 Token／输入／调用限制为 null、整批预算 $2；首轮实际完成全部 18 项，未触及费用停止。后续开始前再确定 Sol 对照、重复次数与预算，并冻结新批次；独立留出任务尚未建立。一次筛查不能当作完成 Plan 13 的全部校准。

## 首轮付费筛查结果：2026-11-03

| 模型 | 全通过 | 完整验收失败 | 未完成／环境 | 估算 USD | 累计运行秒 |
|---|---:|---:|---:|---:|---:|
| DeepSeek low | 8/9 | 1 | 0 | 0.546916200 | 2381.093 |
| Luna medium | 5/9 | 4 | 0 | 0.139305170 | 1559.718 |

每格一次、全部四轮完成、用量完整；整批估算 $0.686221370。没有调参、付费重跑或将最终隐藏反馈喂回模型。Token 累计分别为 7,358,739 和 4,683,945，生成调用 206 和 187 次；累计量不是单次上下文大小。费用按冻结 catalog 估算，DeepSeek 使用峰值价格，不是实际账户账单。

两者均通过三项 TinyDB、容量调整和令牌策略。迁移专项两者均 53/57，遗漏跨格式回退。另三题有质量差异：签名组合 DeepSeek 177/177、Luna 151/177；原子更新 DeepSeek 34/34、Luna 29/34；缓存组合 DeepSeek 79/79、Luna 73/79。Luna 的缓存失败集中于 TTL 回滚后访问异常。

这轮证明候选任务可以暴露完整交付中的遗漏，不再全部满分；**没有证明稳定模型排名或 Sol 的优势**。专项与组合需求重叠，不能把四项失败当作四种独立缺陷。DeepSeek 的签名组合通过、迁移专项却失败，同样说明需要重复验证，不能预设组合题的难度一定更高。

完整证据：[比较报告](../artifacts/python-calibration-live-20261102-01/comparison.md)、[分组与逐项数据](../artifacts/python-calibration-live-20261102-01/comparison.json)、[原始报告](../artifacts/python-calibration-live-20261102-01/report.md)。汇总工具为 [summarize_calibration_comparison.py](../scripts/summarize_calibration_comparison.py)，只读既有记录，不调用模型。

## Sol 对照与后续：2026-11-03

[Sol 单体配置](../configs/workflow-python-calibration-sol.json) 的九题首轮已完成：9/9 全通过、166 次调用、3,378,551 累计 Token，估算 $1.5406067，累计 1,148.610 秒；用量完整，无停止或付费重跑。medium 档位，本地生成与执行额度为 null，整批费用上限 $5；独立 [模型目录](../configs/models-python-calibration-sol.json) 记录服务元数据与长上下文计价，不修改前批。

[三模型报告](../artifacts/python-calibration-three-models-20261103-01/comparison.md) 合并 27 项现有记录：Sol 9/9、DeepSeek 8/9、Luna 5/9。冻结的任务、四轮流程、运行器、本地额度策略和角色权限已核对一致；模型档位、费率、实际缓存、批次预算及执行顺序不同，不能称为相同推理预算或完全交错实验。

后续顺序已记入 [Plan 13](decisions/013-task-discrimination-and-calibration.md)：四个固定关键任务、三模型各再独立运行两次，连同首轮（含失败）累计三次；再根据稳定性决定架构对照。重复已执行并完成下面的整理，架构测试尚未启动，当前不能声称架构省钱。

## 四题重复与中断继续

原重复批次完成17项后，在 Luna 签名组合的一条请求中断；1条请求响应／用量不明，未重跑、未追加隐藏评分。用户要求继续后，只完成原计划中尚未开始的6项，保留原顺序、任务、模型与编号，沿用原 $5 总预算并预留未知费用。

含四题首轮共36项记录，其中35项有最终验收、1项中断：DeepSeek 11/12 全通过，Sol 10/12，Luna 3/11，Luna 另有1项缺失。仅本次新增的有效验收分别为 8/8、6/8、3/7。原五道未重复任务仍各一次，不混合分母。

Sol 迁移题从首轮通过变为两次失败，DeepSeek 从首轮失败变为两次通过；这批数据没有保持首轮对 Sol 稳定性的印象。不能据此作全局排名，也不能预设更贵的 Planner 会提高可靠性。恢复时段和缓存条件变化也是成本／耗时比较的边界。

新增已知费用 $2.298355854，其中继续6项为 $0.521644124；未知请求另预留 $0.067128875，仍在原 $5 上限内。完整记录见 [重复报告](../artifacts/python-calibration-repeat-live-20261103-01/repeat-comparison.md)、[机器数据](../artifacts/python-calibration-repeat-live-20261103-01/repeat-comparison.json)、[恢复记录](../artifacts/python-calibration-repeat-recovery-20261103-01/recovery.json)。缺失结果不伪装成失败或补齐，所有费用均为冻结费率估算。

## Sol／Luna 架构探索

[架构配置](../configs/workflow-python-architecture-sol-luna.json) 使用同四题、原四轮和模型档位，三种结构各一次，共12项。本批已全部完成、用量完整，无调参或重跑：Sol 单体3/4、$0.7759329；Luna 单体1/4、$0.061187590；Sol 规划后 Luna 接管3/4、$0.286004300。总估算 $1.123124790。

交接与 Sol 的逐题分数一致，费用低约63.1%，但调用、累计 Token 和耗时更多；与 Luna 比较则提高了本轮完成数、费用也更高。迁移题仍三组都失败，不能声称完成全部需求。每格仅一次，尚待架构重复与独立评估，不将本轮当作稳定排名或最优结构证明。[本轮报告](../artifacts/python-architecture-sol-luna-live-20261103-01/architecture-comparison.md)、[Plan 13 完整解释](decisions/013-task-discrimination-and-calibration.md)。
