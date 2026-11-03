# 运行时容量调整与淘汰策略一致性

运行时容量调整与淘汰策略一致性：在现有项目包内实现需求，保持只读 app.py 的协议。

1. 新增 Cache.resize(maxsize)，由 Cache/FIFOCache/LRUCache/LFUCache/TTLCache 继承可用。maxsize 仅接受正整数，不接受 bool；非法参数抛 ValueError 且不改变容量、内容或淘汰顺序。

2. 扩容保留所有现有项；缩容使用该实例原 popitem 淘汰策略，直到 currsize<=新容量，再生效新 maxsize；返回按实际淘汰顺序排列的 (key,value) 列表。相同容量不应淘汰。默认 Cache 依照原映射顺序淘汰。

3. 大小使用现有 getsizeof 权重，不能将条目数当 currsize；可能需要淘汰多个条目。缩容后新写入继续遵守新容量，过大值仍抛 ValueError，不能破坏旧内容。

4. FIFO 保留插入顺序，LRU 保留访问顺序，LFU 保留访问频率；不规定 LFU 同频淘汰顺序。TTLCache 先清理过期项，再缩容；自然过期项不计入 resize 返回的容量淘汰列表，原有存活项的截止时间不延长。

5. 调整后 __getitem__/__setitem__/popitem/maxsize/currsize 与 cached 装饰器继续协作；支持可注入的虚拟 timer。不要求线程安全或 pickle 格式兼容。

这是人工整理的新功能合同，不是上游原始 issue。只需 Python 标准库和附带源码；不需要 pip 安装、网络或额外服务。原上游 pytest 测试供阅读，受支持的执行验收为 tests_lab 公开场景。允许使用工具反复测试和修复。
