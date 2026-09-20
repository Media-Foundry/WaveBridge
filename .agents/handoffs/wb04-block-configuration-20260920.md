# block字段与恢复模型的一致性

- 日期2026-09-20；分支wb03-source-ast，基线388205f；中文、直接commit。
  已获稳定提交定期推送授权，不创建PR或合并master。
- 新增verification/block_configuration.py，API读取chain/site及显式integer ABI、
  axis_binding。按精确kernel/launch/constructor IDs连接；三个轴字段必须不同且
  完整覆盖record。调用独立constructor_values，按实际字段映射和转换得到值，
  再比较(x,y,z)=(block_threads,1,1)。不看字段名字，不仅比较维度乘积。
- 测试覆盖合法256/1/1，字段交换成1/256/1，多维16/16/1，线程模型128，缺失/
  重复轴字段、错kernel/ABI、错误命名空间/字段覆盖及畸形hash输入。
  `make check`312项通过；无GPU执行。Sol只读审查后补充了轴协议schema和hash硬化。
- 真实HIP报告沿用artifacts/wb03-shared-binding-02/report.json，未重新伪造AST。
  独立artifact `artifacts/wb04-block-configuration-4atXhg/axis-binding-reviewed.json`显式
  指定此AST的三个FieldDecl与轴对应，并绑定源报告字节hash。该选择是外部API
  协议，不计入自动恢复，不使用人工kernel计算oracle。
- 实际命令 `PYTHONPATH=src python artifacts/wb04-block-configuration-4atXhg/check_reviewed.py`。
  结果checked，dimensions=(256,1,1)；report-reviewed.json SHA256
  `36a8fe33ba55a725ac32fe520cc6b776e9797896e735e4b4aaa7311f9596ad14`。
  未带schema的初次轴工件及报告保留为历史记录，最终API要求launch-axis-assumptions/v1。
  工件保存源报告/ABI/轴协议和实现hash；不可跨AST复用Clang ID。
- 未建立：轴字段与真实launch API的语义、kernel读取的线程坐标、host实际执行
  此launch、目标ABI。source_program_checked/deployable均false。
- 未将本API自动并入容量CLI；避免旧容量报告含义被隐式扩大。下一步应从实际
  getter链绑定线程起点语义，形成可审计外部builtin协议，而非凭threadIdx名字猜值。
