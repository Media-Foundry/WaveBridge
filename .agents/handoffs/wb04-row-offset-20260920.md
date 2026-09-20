# 行偏移整数关系交接

- 日期/分支/基线：2026-09-20，`wb03-source-ast`，`8778335`。
- 用户约定：中文、直接commit、验收后push当前分支；不创建PR、不合并master。
- 实现：row-prefix保存两处完整offset_ast/update_ast；Sol实现独立row_offset及
  9项测试；主代理实现row_offset_check，fresh调用row/thread/column门控，按
  同root/kernel/launch/ABI与精确row/count/start声明连接两处表达式。
- 保证：受限非负整数表达式的符号乘积恰row*count，转换在给定域内值保持、
  乘法无溢出。可能溢出unknown，错误符号关系或窄化rejected；拒绝诊断不是
  可达运行输入证明。Paren仅prvalue支持；128节点/深度32。所有部署标记false。
- 验证：`make check`最终444项通过（3.429秒）；`git diff --check`通过。
  Sol只读审查未发现组合错绑；建议后补齐kernel/launch/host flag输入hash，
  并明确counterexample_scope。未扩展lvalue括号子集。
- 真实验收命令：
  `PYTHONPATH=src python3 artifacts/wb04-row-offset-bLZgDu/final.py`
  退出0；row[0,7]、count[1,1023]，两处offset都是long类型、范围[0,7161]，
  每处5个转换检查。报告绑定原AST、ABI、外部协议、实现及runner哈希；src
  实现hash运行前后一致。final.py仅将原runner输出目录改为final，另存
  runner-provenance.json绑定实际执行文本，不覆盖第一轮报告。
- 最终报告：`artifacts/wb04-row-offset-bLZgDu/final/report.json`，SHA256
  `202cf5bcf0bc1bc335f358eaceca608e232d9e83d3106722172e125d9591b75c`。
  首轮报告在同目录上层，基于审查硬化前实现，保留但不作为最终提交证据。
- 输入：`artifacts/wb03-initializer-value-02/ast.json`，SHA256
  `b9392df45575e1c4bf818ef1bf982c1b0dd2b76e3905f9da0ed6dd05c772a70e`。
  复用row-coordinate-0WHtJN/binding.json和thread-start-psY2gK/binding-final.json；
  新示例`examples/abi/row-offset-conditional.json`增加显式long64假设，未改旧ABI。
- 未执行：新HIP编译、GPU、性能、完整候选源码等价。外部API/ABI、可信前端及
  实际launch配置仍为前提。矩形域不能代替逐launch的row<nrows相关性；整数
  RHS正确不证明指针加法、allocation、alias、列数据访问、参与或浮点结果。
- 下一步：建立每次launch的row/grid/count关联，并连接显式数组容量/输入契约。
  已只读确认baseline中count=size_t(nrows)*ncols、bytes=count*sizeof(float)，
  两次hipMalloc使用bytes，grid使用nrows；这仅是源码定位，尚无绑定检查。
  不得用全域最大偏移7161去声称较小输入的分配足够。
- 提交范围：本轮源码、测试、ABI示例、协议/状态/交接；artifacts仍本地忽略。
  总目标未完成，自动候选到GPU闭环和实际研究差异仍需推进。
