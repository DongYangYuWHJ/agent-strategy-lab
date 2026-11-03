from copy import deepcopy
from cases import (transactions, snapshots, claims, migrations, resizes, atomics,
                   database_integration, signing_integration, cache_integration)


TASKS = [
    dict(id="python-tinydb-transactions", repo="msiemens/tinydb", ref="v4.8.0", package="tinydb",
         module="tinydb/database.py", anchor="class TinyDB(TableBase):\n", implementation="tinydb_transaction.py",
         adapter="database_app.py", cases=transactions, title="跨表事务、嵌套保存点与缓存回滚",
         acceptance=[
             "新增 TinyDB.transaction() 上下文管理器，yield 当前数据库。正常退出提交，异常退出撤销并传播异常；作用于整个数据库，覆盖多个表的 insert/update/remove。已有非事务 API 保持可用。",
             "事务内可读取自己的修改，但底层 storage 在提交前不得收到中间写入；成功最外层事务只调用底层 write 一次（空事务也提交一次），失败最外层事务零次。此处底层指原本交给 TinyDB 的 Storage，不要求进程崩溃恢复、并发隔离或文件系统级原子性。",
             "嵌套事务是保存点：内层失败只撤销内层；被外层捕获后可以继续。内层成功仍属于外层，外层失败时一并撤销，不提前写入真实 Storage。",
             "事务前取得的 Table 句柄在事务内外持续可用。回滚同时恢复数据、查询缓存和自动 ID 状态；被撤销的插入不能消耗未来 ID。支持事务内新建表。",
             "MemoryStorage、JSONStorage、CachingMiddleware(JSONStorage) 行为一致；文件存储关闭重开后保留已提交结果。验收不涉及事务内 close、drop_table/drop_tables、外部持有的新建后已撤销表句柄或实际 I/O 故障。"],
         mutants=[("stale-id", "table._next_id = None", "pass  # missing ID invalidation")]),
    dict(id="python-tinydb-snapshots", repo="msiemens/tinydb", ref="v4.8.0", package="tinydb",
         module="tinydb/database.py", anchor="class TinyDB(TableBase):\n", implementation="tinydb_snapshot.py",
         adapter="database_app.py", cases=snapshots, title="数据库快照恢复、冲突策略与无副作用预检",
         acceptance=[
             "新增 export_snapshot() 返回 {'version':1,'tables':{表名:[{'id':正整数,'data':文档对象},...]}}；包含已存储空表。按表名、ID 升序输出。导出内容须深拷贝，不与数据库共享可变对象。",
             "新增 restore_snapshot(snapshot, mode='replace', dry_run=False)。replace 用快照替换整个库；merge 保留其他文档，同表同 ID 用快照覆盖；reject 保留其他文档，但任一同表同 ID 冲突均抛 ValueError，整个操作不写入。返回操作后 {'tables':表数,'documents':文档总数}。",
             "先完整校验再写入：顶层仅 version/tables，version 为整数1（不接受 bool），tables 为对象；表名是非空字符串，值是列表；每行仅 id/data，id 是正整数且同表不重复（不接受 bool），data 为对象。其他形式抛 ValueError，包括某些表有效但后续表无效。",
             "仅支持三个 mode，dry_run 必须为 bool；非法参数抛 ValueError。dry_run=True 仍校验并计算同样的摘要，但不得改变数据、ID、缓存或存储。输入快照恢复后再被修改，不得改变库。",
             "恢复后已取得的 Table 句柄和查询缓存看到新状态，下一自动 ID 按恢复后当前最大 ID 加一（空表从1）；支持内存、JSON、CachingMiddleware，文件库重开后结果一致；原 insert/search/update/remove 行为保持。"],
         mutants=[("ignore-conflict", 'if mode == "reject" and key in target:', 'if False:  # silently overwrite conflicts')]),
    dict(id="python-itsdangerous-token-policy", repo="pallets/itsdangerous", ref="2.2.0", package="src/itsdangerous",
         module="src/itsdangerous/serializer.py", anchor="class Serializer(t.Generic[_TSerialized]):\n",
         implementation="claims.py", adapter="signing_app.py", cases=claims, title="签名令牌的用途、激活时间与过期策略",
         acceptance=[
             "在 Serializer 及 URLSafeSerializer、TimedSerializer、URLSafeTimedSerializer 上新增 dumps_claims(payload, *, audience, now, ttl, not_before=None) 与 loads_claims(token, *, audience, now, leeway=0)，复用原签名/序列化机制，不改变 dumps/loads。",
             "签名封装精确为 {'v':1,'aud':audience,'iat':now,'nbf':not_before或now,'exp':now+ttl,'payload':payload}。audience 非空字符串；now/ttl/nbf 必须是整数但不接受 bool，ttl>0，iat<=nbf<exp。非法签发参数抛 ValueError。JSON 标量、对象、列表及压缩长字符串均可作为 payload。",
             "读取必须先验签，再校验精确字段、版本、时间字段类型、iat<=nbf<exp 及 audience。签名、salt、密钥错误，或已签名但结构非法、用途错误时抛 BadSignature。不能用 loads_unsafe 绕过签名。",
             "now 和 leeway 必须为整数但不接受 bool，leeway>=0，audience 非空；非法读取参数抛 ValueError。now+leeway>=iat 且 >=nbf 才激活，now<exp+leeway 才未过期；等于过期上限即失效。时间不满足抛 SignatureExpired，成功只返回 payload。",
             "四类序列化器执行同样的显式 claims 时间策略。TimedSerializer 原签名时间继续由其 signer 管理；本 API 不额外给原 loads 传 max_age。原有密钥轮换、salt 隔离和摘要签名继续生效。"],
         mutants=[("expiry-off-by-one", 'now >= data["exp"] + leeway', 'now > data["exp"] + leeway')]),
    dict(id="python-itsdangerous-token-migration", repo="pallets/itsdangerous", ref="2.2.0", package="src/itsdangerous",
         module="src/itsdangerous/serializer.py", anchor="class Serializer(t.Generic[_TSerialized]):\n",
         implementation="migration.py", adapter="signing_app.py", cases=migrations, title="密钥、摘要与用途迁移且不延长原令牌寿命",
         acceptance=[
             "新增 Serializer.migrate(token, *, legacy_serializers=(), max_age=None)，其四种序列化器均可用。legacy_serializers 可为迭代器；依次尝试当前对象（source=0），再尝试显式提供的旧对象（source=1、2…）。只接受经过这些对象真实验签的 payload。",
             "成功返回 {'value':解码内容,'token':重新签发内容,'source':验证对象索引}。新 token 使用当前对象的格式、salt、摘要、最新密钥；允许显式旧配置在 salt/摘要/密钥上不同；当前密钥列表中旧密钥签发的 token 也应迁移到最新密钥。现有 dumps/loads 保持可用。",
             "TimedSerializer 与 URLSafeTimedSerializer 的迁移必须保留原始签名秒数，不能把迁移时间作为新签名时间。迁移后再按 max_age 验证时，剩余寿命不增加；时间戳与原来一致。不得修改全局时钟或其他共享对象。",
             "max_age 非 None 时须为非负整数且不接受 bool，并仅能用于 timed 目标；非法参数抛 ValueError。先验证所有候选类型，均须为 Serializer 实例并与目标同为 timed 或同为非 timed，否则抛 ValueError。允许普通/URL-safe 之间的同类迁移。",
             "验签失败可继续下个候选；验签成功但过期或来自未来时立即传播 SignatureExpired，不继续尝试绕过时效。全部验签失败抛 BadSignature。支持 JSON 标量、嵌套列表/对象、压缩长字符串和调用者自定义 TimestampSigner（验收使用虚拟时钟）。"],
         mutants=[("refresh-timestamp", 'epoch = int(timestamp.timestamp())', 'epoch = int(timestamp.timestamp()) + 1')]),
    dict(id="python-cachetools-resize", repo="tkem/cachetools", ref="v5.3.3", package="src/cachetools",
         module="src/cachetools/__init__.py", anchor="class Cache(collections.abc.MutableMapping):\n",
         implementation="cache_resize.py", adapter="cache_app.py", cases=resizes, title="运行时容量调整与淘汰策略一致性",
         acceptance=[
             "新增 Cache.resize(maxsize)，由 Cache/FIFOCache/LRUCache/LFUCache/TTLCache 继承可用。maxsize 仅接受正整数，不接受 bool；非法参数抛 ValueError 且不改变容量、内容或淘汰顺序。",
             "扩容保留所有现有项；缩容使用该实例原 popitem 淘汰策略，直到 currsize<=新容量，再生效新 maxsize；返回按实际淘汰顺序排列的 (key,value) 列表。相同容量不应淘汰。默认 Cache 依照原映射顺序淘汰。",
             "大小使用现有 getsizeof 权重，不能将条目数当 currsize；可能需要淘汰多个条目。缩容后新写入继续遵守新容量，过大值仍抛 ValueError，不能破坏旧内容。",
             "FIFO 保留插入顺序，LRU 保留访问顺序，LFU 保留访问频率；不规定 LFU 同频淘汰顺序。TTLCache 先清理过期项，再缩容；自然过期项不计入 resize 返回的容量淘汰列表，原有存活项的截止时间不延长。",
             "调整后 __getitem__/__setitem__/popitem/maxsize/currsize 与 cached 装饰器继续协作；支持可注入的虚拟 timer。不要求线程安全或 pickle 格式兼容。"],
         mutants=[("single-eviction", 'while self.currsize > maxsize:', 'if self.currsize > maxsize:')]),
    dict(id="python-cachetools-atomic-update", repo="tkem/cachetools", ref="v5.3.3", package="src/cachetools",
         module="src/cachetools/__init__.py", anchor="class Cache(collections.abc.MutableMapping):\n",
         implementation="cache_atomic.py", adapter="cache_app.py", cases=atomics, title="流式批量更新的原子失败与缓存元数据回滚",
         acceptance=[
             "新增 Cache.update_atomic(pairs)，供 Cache/FIFO/LRU/LFU/TTL 各类使用；pairs 为 (key,value) 对的可迭代对象，可能是一次性生成器。成功的效果与按顺序普通写入相同，返回消费的对数（重复 key 也计数），空输入返回0。",
             "若输入迭代器中途异常、条目无法解包、值超过容量或 getsizeof/写入抛异常，应传播异常，且缓存整体保持调用前状态，不能保留已经插入的前缀或已经淘汰的条目。",
             "原子状态包括数据、currsize、maxsize、FIFO/LRU 淘汰顺序、LFU 访问频率以及 TTL 到期元数据。失败后的下一次 popitem 与没有调用该失败批次时一致；不能只恢复用户字典。",
             "成功仍遵守权重容量与原淘汰策略，重复 key 按顺序更新；TTL 中旧条目不得因为复制/提交延长截止时间，新条目使用当前 timer。保留调用者传入的时钟来源，不得替换成冻结或独立时钟。",
             "更新后普通读写和 cached 装饰器继续使用同一个缓存对象。接口只承诺进程内、单线程、可深拷贝 key/value 的场景；不要求崩溃恢复、线程安全、回滚外部生成器副作用或回滚 getsizeof 的外部副作用。"],
         mutants=[("shallow-rollback", 'from copy import deepcopy\n    staged = deepcopy(self)', 'from copy import copy\n    staged = copy(self)')]),
]

# Keep related contracts explicit: combined tasks are a separate scope, not independent evidence.
for first, second, identifier, title, cases in [
    (0, 1, "python-tinydb-integrated", "事务内快照恢复与跨表兼容交付", database_integration),
    (2, 3, "python-itsdangerous-integrated", "令牌策略与密钥迁移的完整兼容交付", signing_integration),
    (4, 5, "python-cachetools-integrated", "动态容量与原子批量更新的一致性交付", cache_integration),
]:
    left, right = TASKS[first], TASKS[second]
    combined = deepcopy(left)
    combined.update(id=identifier, title=title, scope="integrated", cases=cases,
                    implementation=[left["implementation"], right["implementation"]],
                    acceptance=left["acceptance"] + right["acceptance"] + [{
                        0: "两组功能共用数据库状态：事务内导出读取尚未提交的数据；事务内 restore_snapshot 与普通写入一起提交或回滚；嵌套恢复遵守保存点，dry_run 不消耗 ID 或写入底层 Storage。",
                        2: "两组功能协同：迁移签名封装不改变其 audience/iat/nbf/exp/payload，迁移后 loads_claims 仍按原用途和原过期时间验证；timed 令牌同时保持原签名秒数。",
                        4: "两组功能共用缓存状态：resize 后的 update_atomic 使用新容量；失败批次不撤销已完成的 resize，不改变其内容或淘汰元数据。权重和 TTL 规则继续生效。",
                    }[first]],
                    mutants=left["mutants"] + right["mutants"])
    TASKS.append(combined)
