# 列数域组合检查交接

- 日期/分支：2026-09-20，`wb03-source-ast`；基线 `053318c`。
- 用户约定：始终中文，直接commit，不创建PR；验收后推送当前分支，不合并master。
- 实现：column_coverage增加闭区间API；column_domain_check把真实线程起点证据、
  新恢复的launch位置实参及host guard域连接到区间索引覆盖。只读列数形参和直接
  kernel循环门控避免把launch值错用于已修改的loop bound。
- 验证：`make check`，368项CPU测试通过。新增小整数域穷举交叉验证、1e9上界
  单次检查、零列/重复/遗漏/溢出及同AST绑定、形参逃逸、早退/嵌套负例。
- 真实运行：`PYTHONPATH=src python3 artifacts/wb04-column-domain-Vh20Ku/check.py`。
  从固定原AST重新运行thread_start_check和column_domain_check；两个loop在256
  线程、stride256、列数[1,1023]上条件checked，source_program_checked/deployable
  均false。运行前后全部src实现hash一致，报告同时保存runner/协议/源工件hash。
- 最终报告：`artifacts/wb04-column-domain-Vh20Ku/report.json`，SHA256
  `0ea2a17f9137766f8f29c0fd0db0569033f0a70a2b5a2479c77a491e82c7917b`。
- 原AST：`artifacts/wb03-initializer-value-02/ast.json`，SHA256
  `b9392df45575e1c4bf818ef1bf982c1b0dd2b76e3905f9da0ed6dd05c772a70e`。
  root规范hash `91b528c4ed158ed3d817740a3b5cc4580ab2a28d6436320c3fd1a517a7d1ea57`；
  绑定使用 `artifacts/wb04-thread-start-psY2gK/binding-final.json`，ABI使用
  `examples/abi/storage-conditional.json`。大工件按既有规则仅本地保存、不入Git。
- 审查：GPT-5.6 Sol确认上界提升与bound门控，建议将结论从“列访问”收紧为
  “列索引生成”，已纳入报告和文档；没有宣称数据贡献正确。
- 未执行：新AST编译、GPU、性能测量、自动候选生成、整核/机器码等价。
- 保证边界：host域是必要条件过近似，不保证可达；依赖真实上游报告、可信前端、
  外部API/ABI及运行配置、有效执行和所有模型线程到达循环。hash绑定不是任意
  外部报告的真实性认证。索引覆盖不意味着数组访问/贡献/同步/浮点关系正确。
- 下一步：连接已检查helper索引与shared写入/广播谓词及收敛前提；不能只因列域
  与坐标两个局部门控通过便放行候选。G1差异与完整GPU闭环依然未建立。
