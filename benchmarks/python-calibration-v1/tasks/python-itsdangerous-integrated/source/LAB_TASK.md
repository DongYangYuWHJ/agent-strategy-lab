# 令牌策略与密钥迁移的完整兼容交付

令牌策略与密钥迁移的完整兼容交付：在现有项目包内实现需求，保持只读 app.py 的协议。

1. 在 Serializer 及 URLSafeSerializer、TimedSerializer、URLSafeTimedSerializer 上新增 dumps_claims(payload, *, audience, now, ttl, not_before=None) 与 loads_claims(token, *, audience, now, leeway=0)，复用原签名/序列化机制，不改变 dumps/loads。

2. 签名封装精确为 {'v':1,'aud':audience,'iat':now,'nbf':not_before或now,'exp':now+ttl,'payload':payload}。audience 非空字符串；now/ttl/nbf 必须是整数但不接受 bool，ttl>0，iat<=nbf<exp。非法签发参数抛 ValueError。JSON 标量、对象、列表及压缩长字符串均可作为 payload。

3. 读取必须先验签，再校验精确字段、版本、时间字段类型、iat<=nbf<exp 及 audience。签名、salt、密钥错误，或已签名但结构非法、用途错误时抛 BadSignature。不能用 loads_unsafe 绕过签名。

4. now 和 leeway 必须为整数但不接受 bool，leeway>=0，audience 非空；非法读取参数抛 ValueError。now+leeway>=iat 且 >=nbf 才激活，now<exp+leeway 才未过期；等于过期上限即失效。时间不满足抛 SignatureExpired，成功只返回 payload。

5. 四类序列化器执行同样的显式 claims 时间策略。TimedSerializer 原签名时间继续由其 signer 管理；本 API 不额外给原 loads 传 max_age。原有密钥轮换、salt 隔离和摘要签名继续生效。

6. 新增 Serializer.migrate(token, *, legacy_serializers=(), max_age=None)，其四种序列化器均可用。legacy_serializers 可为迭代器；依次尝试当前对象（source=0），再尝试显式提供的旧对象（source=1、2…）。只接受经过这些对象真实验签的 payload。

7. 成功返回 {'value':解码内容,'token':重新签发内容,'source':验证对象索引}。新 token 使用当前对象的格式、salt、摘要、最新密钥；允许显式旧配置在 salt/摘要/密钥上不同；当前密钥列表中旧密钥签发的 token 也应迁移到最新密钥。现有 dumps/loads 保持可用。

8. TimedSerializer 与 URLSafeTimedSerializer 的迁移必须保留原始签名秒数，不能把迁移时间作为新签名时间。迁移后再按 max_age 验证时，剩余寿命不增加；时间戳与原来一致。不得修改全局时钟或其他共享对象。

9. max_age 非 None 时须为非负整数且不接受 bool，并仅能用于 timed 目标；非法参数抛 ValueError。先验证所有候选类型，均须为 Serializer 实例并与目标同为 timed 或同为非 timed，否则抛 ValueError。允许普通/URL-safe 之间的同类迁移。

10. 验签失败可继续下个候选；验签成功但过期或来自未来时立即传播 SignatureExpired，不继续尝试绕过时效。全部验签失败抛 BadSignature。支持 JSON 标量、嵌套列表/对象、压缩长字符串和调用者自定义 TimestampSigner（验收使用虚拟时钟）。

11. 两组功能协同：迁移签名封装不改变其 audience/iat/nbf/exp/payload，迁移后 loads_claims 仍按原用途和原过期时间验证；timed 令牌同时保持原签名秒数。

这是人工整理的新功能合同，不是上游原始 issue。只需 Python 标准库和附带源码；不需要 pip 安装、网络或额外服务。原上游 pytest 测试供阅读，受支持的执行验收为 tests_lab 公开场景。允许使用工具反复测试和修复。
