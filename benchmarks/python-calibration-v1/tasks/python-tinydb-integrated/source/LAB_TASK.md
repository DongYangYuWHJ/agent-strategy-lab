# 事务内快照恢复与跨表兼容交付

事务内快照恢复与跨表兼容交付：在现有项目包内实现需求，保持只读 app.py 的协议。

1. 新增 TinyDB.transaction() 上下文管理器，yield 当前数据库。正常退出提交，异常退出撤销并传播异常；作用于整个数据库，覆盖多个表的 insert/update/remove。已有非事务 API 保持可用。

2. 事务内可读取自己的修改，但底层 storage 在提交前不得收到中间写入；成功最外层事务只调用底层 write 一次（空事务也提交一次），失败最外层事务零次。此处底层指原本交给 TinyDB 的 Storage，不要求进程崩溃恢复、并发隔离或文件系统级原子性。

3. 嵌套事务是保存点：内层失败只撤销内层；被外层捕获后可以继续。内层成功仍属于外层，外层失败时一并撤销，不提前写入真实 Storage。

4. 事务前取得的 Table 句柄在事务内外持续可用。回滚同时恢复数据、查询缓存和自动 ID 状态；被撤销的插入不能消耗未来 ID。支持事务内新建表。

5. MemoryStorage、JSONStorage、CachingMiddleware(JSONStorage) 行为一致；文件存储关闭重开后保留已提交结果。验收不涉及事务内 close、drop_table/drop_tables、外部持有的新建后已撤销表句柄或实际 I/O 故障。

6. 新增 export_snapshot() 返回 {'version':1,'tables':{表名:[{'id':正整数,'data':文档对象},...]}}；包含已存储空表。按表名、ID 升序输出。导出内容须深拷贝，不与数据库共享可变对象。

7. 新增 restore_snapshot(snapshot, mode='replace', dry_run=False)。replace 用快照替换整个库；merge 保留其他文档，同表同 ID 用快照覆盖；reject 保留其他文档，但任一同表同 ID 冲突均抛 ValueError，整个操作不写入。返回操作后 {'tables':表数,'documents':文档总数}。

8. 先完整校验再写入：顶层仅 version/tables，version 为整数1（不接受 bool），tables 为对象；表名是非空字符串，值是列表；每行仅 id/data，id 是正整数且同表不重复（不接受 bool），data 为对象。其他形式抛 ValueError，包括某些表有效但后续表无效。

9. 仅支持三个 mode，dry_run 必须为 bool；非法参数抛 ValueError。dry_run=True 仍校验并计算同样的摘要，但不得改变数据、ID、缓存或存储。输入快照恢复后再被修改，不得改变库。

10. 恢复后已取得的 Table 句柄和查询缓存看到新状态，下一自动 ID 按恢复后当前最大 ID 加一（空表从1）；支持内存、JSON、CachingMiddleware，文件库重开后结果一致；原 insert/search/update/remove 行为保持。

11. 两组功能共用数据库状态：事务内导出读取尚未提交的数据；事务内 restore_snapshot 与普通写入一起提交或回滚；嵌套恢复遵守保存点，dry_run 不消耗 ID 或写入底层 Storage。

这是人工整理的新功能合同，不是上游原始 issue。只需 Python 标准库和附带源码；不需要 pip 安装、网络或额外服务。原上游 pytest 测试供阅读，受支持的执行验收为 tests_lab 公开场景。允许使用工具反复测试和修复。
