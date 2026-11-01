# 修复分页 API 的边界与元数据

分页接口出现每页少一条、末页页数不一致的问题。请修复已有分页组件，保持 API 返回结构和错误格式，检查空集合、最后一页及非法参数。

- run(request) 接收 items（必填列表）、page（默认1）、page_size（默认20）；不修改请求数据。
- page/page_size 必须为正整数，bool、字符串、浮点数无效；无效返回 {error: invalid_pagination}。
- 返回 items/page/page_size/total/total_pages/has_next；total_pages 向上取整，空集合为0。
- 越过最后一页返回空 items；has_next 仅表示当前页之后还有数据。

入口是 app.run(request)。公开样例在 tests/test_smoke.py，可使用实验工具 run_checks 运行公开验收。
本地开发也可在仓库根目录执行 python -m unittest discover -s tests。无外部依赖、网络或真实等待。
