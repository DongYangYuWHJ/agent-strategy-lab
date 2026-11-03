# 签名令牌的用途、激活时间与过期策略

签名令牌的用途、激活时间与过期策略：在现有项目包内实现需求，保持只读 app.py 的协议。

1. 在 Serializer 及 URLSafeSerializer、TimedSerializer、URLSafeTimedSerializer 上新增 dumps_claims(payload, *, audience, now, ttl, not_before=None) 与 loads_claims(token, *, audience, now, leeway=0)，复用原签名/序列化机制，不改变 dumps/loads。

2. 签名封装精确为 {'v':1,'aud':audience,'iat':now,'nbf':not_before或now,'exp':now+ttl,'payload':payload}。audience 非空字符串；now/ttl/nbf 必须是整数但不接受 bool，ttl>0，iat<=nbf<exp。非法签发参数抛 ValueError。JSON 标量、对象、列表及压缩长字符串均可作为 payload。

3. 读取必须先验签，再校验精确字段、版本、时间字段类型、iat<=nbf<exp 及 audience。签名、salt、密钥错误，或已签名但结构非法、用途错误时抛 BadSignature。不能用 loads_unsafe 绕过签名。

4. now 和 leeway 必须为整数但不接受 bool，leeway>=0，audience 非空；非法读取参数抛 ValueError。now+leeway>=iat 且 >=nbf 才激活，now<exp+leeway 才未过期；等于过期上限即失效。时间不满足抛 SignatureExpired，成功只返回 payload。

5. 四类序列化器执行同样的显式 claims 时间策略。TimedSerializer 原签名时间继续由其 signer 管理；本 API 不额外给原 loads 传 max_age。原有密钥轮换、salt 隔离和摘要签名继续生效。

这是人工整理的新功能合同，不是上游原始 issue。只需 Python 标准库和附带源码；不需要 pip 安装、网络或额外服务。原上游 pytest 测试供阅读，受支持的执行验收为 tests_lab 公开场景。允许使用工具反复测试和修复。
