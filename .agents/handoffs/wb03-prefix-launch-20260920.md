# 交接：行偏移与launch结构

- 日期、分支、基线：2026-09-20，`wb03-source-ast`，`8795002`。
- 用户约定：中文、直接commit、不创建PR；未推送。
- 实现：`row_prefix`复用后缀关系，核对严格四语句前缀的row/start和input/output偏移；比较完整statement/row/count cast signatures及乘积类型。`offset_integer_width`与坐标语义保持未建立。
- 实现：`launch_facts`保存目标kernel的精确同root launch引用、配置调用及kernel实参AST，不求dim3值、不判定host可达性或配置正确。
- 验证：`make check`190项通过，`git diff --check`通过；真实Clang前缀及wrong-row回归、单侧乘积外层转换拒绝、间接launch与缺配置未知。
- 实际HIP：沿用wb03-discovery完整源码入口命令，输出改为 `artifacts/wb03-source-prefix-launch-01`。prefix recovered，10处offset casts，两个初始化各1条调用；1个launch含4个配置与4个kernel实参。AST及实现hash核对一致。
- 边界：前缀结构对应不等于row/block和start/thread语义证明，指针范围和位宽仍需目标契约。launch仅结构证据。未执行新GPU/native64/性能实验，未生成候选。
- 下一步：解析launch的维度构造及实参与kernel参数对应，在已建立目标ABI/坐标协议下检查列覆盖与输出行归属；完整源/目标检查和G1差异验证仍缺证据。
