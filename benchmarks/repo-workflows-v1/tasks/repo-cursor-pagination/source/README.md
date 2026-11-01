# 定位相同时间戳下游标翻页的数据丢失

事件接口在相同 created_at 的记录之间翻页会丢数据或重复，无效游标还会静默从头开始。请定位排序、筛选和错误处理链路中的问题，保持既有游标格式。

- run(request) 接收 records、limit（默认2）、cursor（默认null），不修改输入。每条记录 id 是唯一正整数、created_at 为整数，其余字段原样保留。
- 按 (created_at,id) 升序分页，使用严格大于游标二元位置的记录；合法游标不要求对应现有记录。limit 为正整数且不接受 bool，否则返回 {error:invalid_limit}。
- 返回 items 和 next_cursor；只有仍有后续记录时返回本页最后记录的游标，否则为null；空结果不得生成游标。
- 沿用只读 tokens.py 的 v1 URL-safe Base64 JSON 格式；无效编码、字段或版本返回 {error:invalid_cursor}，不静默重置。先验证limit，再解析游标。

入口是 app.run(request)。公开样例在 tests/test_smoke.py，可使用实验工具 run_checks 运行公开验收。
本地开发也可在仓库根目录执行 python -m unittest discover -s tests。无外部依赖、网络或真实等待。
