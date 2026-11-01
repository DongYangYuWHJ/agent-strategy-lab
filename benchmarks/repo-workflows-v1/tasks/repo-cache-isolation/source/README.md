# 定位文档缓存的租户串数据与返回值污染

同编号文档在切换租户后偶尔显示错误标题；管理员先访问后，普通用户偶尔看到管理字段；调用方修改返回对象后，下一次读取也被污染。请定位并修复，保留有效缓存和局部失效。

- run(request) 接收 documents 与 actions，返回 results 和实际 repository_reads；不修改请求。文档以 tenant/id 唯一，操作只涉及已存在文档，role 为 admin/viewer。
- read 返回 id/title，只有 admin 可见 secret；租户、文档、权限不同的结果不能混用。相同读取应命中缓存，不能直接关闭缓存。
- mutate_last 模拟调用方修改上次返回对象的 field/value，返回 {ok:true}，不应污染缓存或仓库；results 中保存的是各次调用当时的快照。
- update 只改指定 tenant/id 的 title，返回 {ok:true}；应失效该文档所有角色结果，其他文档与租户缓存保持有效。

入口是 app.run(request)。公开样例在 tests/test_smoke.py，可使用实验工具 run_checks 运行公开验收。
本地开发也可在仓库根目录执行 python -m unittest discover -s tests。无外部依赖、网络或真实等待。
