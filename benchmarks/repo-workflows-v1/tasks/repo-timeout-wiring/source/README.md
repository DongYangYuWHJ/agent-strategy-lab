# 贯通命令行、配置与传输层的超时设置

给已有客户端增加 --timeout-ms 与 APP_TIMEOUT_MS 支持，确保配置选择、毫秒转换及请求展示贯通，保留 --target、User-Agent 和原有默认行为。

- run(request) 接收 argv/config/env（默认空）；不修改输入。argv 仅含已声明的 --target 与 --timeout-ms，不要求支持其他命令。
- timeout_ms 优先级为 CLI > APP_TIMEOUT_MS 环境映射 > config.timeout_ms > 默认1000；选中高优先级无效值必须报错，不退回低优先级。
- 各来源接受非负整数或去除两端空白后的ASCII十进制数字字符串；bool/浮点/null/负数/空字符串无效，返回 {error: invalid_timeout}。
- 0 表示禁用超时，传输层 timeout_seconds 为null；否则毫秒除以1000。返回 target/timeout_ms/timeout_seconds/headers，保留 User-Agent: lab-client/1。

入口是 app.run(request)。公开样例在 tests/test_smoke.py，可使用实验工具 run_checks 运行公开验收。
本地开发也可在仓库根目录执行 python -m unittest discover -s tests。无外部依赖、网络或真实等待。
