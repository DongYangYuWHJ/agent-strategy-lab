# 修复 HTTP 重试的次数与等待策略

HTTP 客户端会对永久错误反复重试，重试耗尽后仍然等待。请修复现有重试策略，保持 transport 与虚拟 clock 的接口。

- run(request) 接收非空 responses 列表、max_attempts（默认3）、base_delay（默认1），返回 status/body/attempts/delays；不修改输入。
- 仅 429/500/502/503/504 可重试；max_attempts 包含第一次请求，必须为正整数且不接受 bool；base_delay 为非负有限数字且不接受 bool；无效返回 {error: invalid_retry_options}。
- 第n次失败后的默认等待为 base_delay * 2**(n-1)；非负数值 retry_after 优先（包括0）；其他 retry_after 忽略。
- 成功、永久错误、最后一次尝试之后均不等待。响应列表不足时 transport 重复最后一个响应；body 缺失时为null。无需真实网络或睡眠。

入口是 app.run(request)。公开样例在 tests/test_smoke.py，可使用实验工具 run_checks 运行公开验收。
本地开发也可在仓库根目录执行 python -m unittest discover -s tests。无外部依赖、网络或真实等待。
