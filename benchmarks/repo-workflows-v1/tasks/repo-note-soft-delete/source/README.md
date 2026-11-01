# 为笔记服务增加软删除与恢复

现有笔记服务会永久删除记录。增加软删除与恢复，并让列表、详情、创建冲突和更新行为保持一致，不丢失原始内容。

- run(request) 接收 notes 和 operations（默认空），按顺序处理，返回 {results: [...]}；不修改输入。笔记 id 为唯一非空字符串，text 为字符串，初始 deleted 默认为false。
- 支持 list/get/delete/restore/create/update；所有笔记展示包含 id/text/deleted，列表保持初始及创建的插入顺序。
- delete 只标记 deleted=true，重复删除仍返回 {ok:true}；restore 恢复原内容，对未删除记录也幂等成功。不存在返回 {error:not_found}。
- list/get 默认屏蔽已删除记录；显式 include_deleted=true 才展示。update 只能更新未删除记录。
- create 与任意已有 id（含已删除）冲突时返回 {error:conflict}；成功返回新笔记。update 成功返回更新后的笔记。

入口是 app.run(request)。公开样例在 tests/test_smoke.py，可使用实验工具 run_checks 运行公开验收。
本地开发也可在仓库根目录执行 python -m unittest discover -s tests。无外部依赖、网络或真实等待。
