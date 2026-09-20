# Row 初始化式与 grid 域交接

- 日期/分支/基线：2026-09-20，`wb03-source-ast`，`940eb98`。
- 用户约定：中文、直接commit、阶段性push，不创建PR或合并master。
- 本轮：新增row_coordinate_check，fresh grid+row-prefix恢复；从源码row初始化
  value_link连接getter与初始化域checker。row-coordinate-assumptions/v1只提供
  外部group-id协议及嵌套grid绑定，不输入人工row声明ID/数值上界。
- 验证：`make check`428项CPU测试通过；Sol编写7项组合测试并只读审查实现，
  覆盖错root/kernel/launch/axis、非一维grid、prefix失败、getter/initializer窄化。
- 命令：`PYTHONPATH=src python3 artifacts/wb04-row-coordinate-0WHtJN/check.py`。
  从原AST重新恢复grid和row表达式，条件checked，row_interval=[0,7]。运行前后
  src实现hash一致，source_program_checked/deployable均false。
- 报告：`artifacts/wb04-row-coordinate-0WHtJN/report.json`，SHA256
  `7b829e803f0e8f44f5fbf686852b434582935830eb69655113a753b7ce589f8a`。
  同目录binding.json与runner；报告保存AST/ABI/绑定/实现/runner hash。
- 输入：artifacts/wb03-initializer-value-02/ast.json，SHA256
  `b9392df45575e1c4bf818ef1bf982c1b0dd2b76e3905f9da0ed6dd05c772a70e`；
  integer ABI仍为examples/abi/storage-conditional.json。外部leaf为同AST
  `0x2d2b6d10`，来源与HIP规范核查见wb04-grid-domain-20260920交接。
- 未执行：新HIP编译、GPU、性能、源/目标候选等价。
- 边界：checked描述明确外部API/ABI、真实运行配置和可信前端下的初始化值关系。
  不证明receiver/调用点有效性；跨grid域的[0,7]不能单独用于逐输入行边界证明。
  row与nrows相关性、row*ncols转换/算术、指针范围、别名、参与及浮点仍未建立。
- 下一步：保留row-prefix两处offset完整AST，独立检查row*ncols中的整数转换
  与乘法范围，再连接外部数组输入域；不要只比较剥除转换后的结构或整数区间。
