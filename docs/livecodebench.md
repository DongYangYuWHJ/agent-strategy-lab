# LiveCodeBench 单 Agent 任务与验收

已准备六道真实任务：easy、medium、hard 各两道。它们用于检查输入、代码产物、公开反馈与最终验收是否可用；数量与来源分布尚不足以用于模型能力排名或架构结论。此次没有调用任何付费模型。

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
