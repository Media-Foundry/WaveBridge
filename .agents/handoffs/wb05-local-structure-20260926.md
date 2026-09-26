# 交接：双侧局部 typed AST 模板

- 日期、分支和基线：2026-09-26，wb03-source-ast，35a077e；开始时工作树干净。
- 用户目标：持续推进真实源码闭环，中文回复，直接commit及push当前分支，不建PR。
- 已完成：新增verification/local_structure.py，从两侧root/kernel fresh恢复局部
  贡献，比较自动accumulator声明与完整ForStmt。只删除显式展示元数据；类型、
  cast、compute type、operator/operand order、FP字段保留。未知字段/节点、
  缺类型、重复声明、超预算unknown。角色ID单射，参数位置纳入模板。
- 常量：非role引用经独立evaluate求值；直接及sources列出的递归依赖声明全部
  核验唯一性。旧独立constant evaluator本身未改动，本模块在消费边界核验。
- 集成：compare_rmsnorm_routes报告v2，fresh routes之后强制fresh局部比较，
  local unknown/rejected阻止整体evidence；不解除entry/consumer/leaf对应义务。
- 测试：make check最终798项、62.970秒，匹配AOCC17 native插件启用；demo和
  git diff --check通过。8项新真实Clang/变体方法、1项新增mock组合方法。
  包含参数替换、常量改值、未知字段、compute/FP字段、持久变量、前缀/consumer
  排除边界，以及递归声明冲突。没有把基于真实AST的合成突变称为编译器输出。
- 复现过的加固缺口：初版只查直接常量ID，间接依赖重复ID合成负例得到evidence；
  transitive-before.log保存失败，修复后8项专项全部通过。没有删除失败证据。
- 真实输入：此前固定的HIP source/target AST及两侧显式API/ABI协议，逐SHA核验；
  不读取旧成功报告。首轮完整重放296.21秒，最终加固后重放295.96秒；均退出0。
  最终local模板相同，贡献重数相同，ordered add DAG不同；leaf仍not_established。
- 工件：artifacts/wb-local-structure-hfn1Di/，本地忽略目录不上传大文件。
  复现命令：PYTHONPATH=src python3 artifacts/wb-local-structure-hfn1Di/run.py report-final.json
  （输出已存在时拒绝覆盖；重放需另取输出名）。测试日志为tests-final.log。
- 最终报告SHA：3de8725dc1c9fe524a467bb8aff16fa5c2b345db6af6c2d85d729cde116d443a。
  源/目标模板SHA同为f7747030ed728f7d5597072126c188574f560c0a1f546cf3b90358b3f25b62c6；
  比较依据为实际模板相等，不是仅比hash。实现文件hash前后稳定。
- 实现SHA：local_structure.py=12f95e5faabd782e0945994bfec618d80082418e32e3f16296f809e7d76d0a40；
  device_evidence.py=300bea8bac57c0831bce68f44240babf04863c05173e416d4b0d1694db37b754。
- 协作：既有GPT-5.6 Sol只读复核，指出的递归依赖身份边界已补测试和修复。
- 没有执行：新的HIP AST采集、GPU编译/执行、数值/性能评测。
- 保证边界：prefix和consumer不在模板内；修改input前缀或consumer可仍结构同构，
  测试明确保留入口/consumer/叶值未对应。FP环境、指针/alias、整数域、有效源
  和机器码都需另证。rejected是结构条件不满足，不是数值反例。整核/部署false。
  节点预算只约束初次清单与片段深度，不是所有子恢复的总资源预算。
- 待提交：两实现、两测试、验证器/架构/状态文档及本交接。
- 下一步：将双侧前缀、坐标与kernel参数对应接入role绑定，补入口值关系；
  不将两个成功模板换名当作已解除source leaf等价，更不放行W7900 native64。
