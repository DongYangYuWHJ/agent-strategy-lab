# 动态容量与原子批量更新的一致性交付

动态容量与原子批量更新的一致性交付：在现有项目包内实现需求，保持只读 app.py 的协议。

1. 新增 Cache.resize(maxsize)，由 Cache/FIFOCache/LRUCache/LFUCache/TTLCache 继承可用。maxsize 仅接受正整数，不接受 bool；非法参数抛 ValueError 且不改变容量、内容或淘汰顺序。

2. 扩容保留所有现有项；缩容使用该实例原 popitem 淘汰策略，直到 currsize<=新容量，再生效新 maxsize；返回按实际淘汰顺序排列的 (key,value) 列表。相同容量不应淘汰。默认 Cache 依照原映射顺序淘汰。

3. 大小使用现有 getsizeof 权重，不能将条目数当 currsize；可能需要淘汰多个条目。缩容后新写入继续遵守新容量，过大值仍抛 ValueError，不能破坏旧内容。

4. FIFO 保留插入顺序，LRU 保留访问顺序，LFU 保留访问频率；不规定 LFU 同频淘汰顺序。TTLCache 先清理过期项，再缩容；自然过期项不计入 resize 返回的容量淘汰列表，原有存活项的截止时间不延长。

5. 调整后 __getitem__/__setitem__/popitem/maxsize/currsize 与 cached 装饰器继续协作；支持可注入的虚拟 timer。不要求线程安全或 pickle 格式兼容。

6. 新增 Cache.update_atomic(pairs)，供 Cache/FIFO/LRU/LFU/TTL 各类使用；pairs 为 (key,value) 对的可迭代对象，可能是一次性生成器。成功的效果与按顺序普通写入相同，返回消费的对数（重复 key 也计数），空输入返回0。

7. 若输入迭代器中途异常、条目无法解包、值超过容量或 getsizeof/写入抛异常，应传播异常，且缓存整体保持调用前状态，不能保留已经插入的前缀或已经淘汰的条目。

8. 原子状态包括数据、currsize、maxsize、FIFO/LRU 淘汰顺序、LFU 访问频率以及 TTL 到期元数据。失败后的下一次 popitem 与没有调用该失败批次时一致；不能只恢复用户字典。

9. 成功仍遵守权重容量与原淘汰策略，重复 key 按顺序更新；TTL 中旧条目不得因为复制/提交延长截止时间，新条目使用当前 timer。保留调用者传入的时钟来源，不得替换成冻结或独立时钟。

10. 更新后普通读写和 cached 装饰器继续使用同一个缓存对象。接口只承诺进程内、单线程、可深拷贝 key/value 的场景；不要求崩溃恢复、线程安全、回滚外部生成器副作用或回滚 getsizeof 的外部副作用。

11. 两组功能共用缓存状态：resize 后的 update_atomic 使用新容量；失败批次不撤销已完成的 resize，不改变其内容或淘汰元数据。权重和 TTL 规则继续生效。

这是人工整理的新功能合同，不是上游原始 issue。只需 Python 标准库和附带源码；不需要 pip 安装、网络或额外服务。原上游 pytest 测试供阅读，受支持的执行验收为 tests_lab 公开场景。允许使用工具反复测试和修复。
