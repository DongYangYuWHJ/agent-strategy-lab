# 数据库快照恢复、冲突策略与无副作用预检

数据库快照恢复、冲突策略与无副作用预检：在现有项目包内实现需求，保持只读 app.py 的协议。

1. 新增 export_snapshot() 返回 {'version':1,'tables':{表名:[{'id':正整数,'data':文档对象},...]}}；包含已存储空表。按表名、ID 升序输出。导出内容须深拷贝，不与数据库共享可变对象。

2. 新增 restore_snapshot(snapshot, mode='replace', dry_run=False)。replace 用快照替换整个库；merge 保留其他文档，同表同 ID 用快照覆盖；reject 保留其他文档，但任一同表同 ID 冲突均抛 ValueError，整个操作不写入。返回操作后 {'tables':表数,'documents':文档总数}。

3. 先完整校验再写入：顶层仅 version/tables，version 为整数1（不接受 bool），tables 为对象；表名是非空字符串，值是列表；每行仅 id/data，id 是正整数且同表不重复（不接受 bool），data 为对象。其他形式抛 ValueError，包括某些表有效但后续表无效。

4. 仅支持三个 mode，dry_run 必须为 bool；非法参数抛 ValueError。dry_run=True 仍校验并计算同样的摘要，但不得改变数据、ID、缓存或存储。输入快照恢复后再被修改，不得改变库。

5. 恢复后已取得的 Table 句柄和查询缓存看到新状态，下一自动 ID 按恢复后当前最大 ID 加一（空表从1）；支持内存、JSON、CachingMiddleware，文件库重开后结果一致；原 insert/search/update/remove 行为保持。

这是人工整理的新功能合同，不是上游原始 issue。只需 Python 标准库和附带源码；不需要 pip 安装、网络或额外服务。原上游 pytest 测试供阅读，受支持的执行验收为 tests_lab 公开场景。允许使用工具反复测试和修复。
