# 交接：属性 receiver 与 getter 条件无写组合

- 日期、分支、基线：2026-09-22，wb03-source-ast，d1c5285；中文回复、直接commit/push。
- 目标：处理此前 blockIdx.x 属性访问的 receiver 求值缺口，不把static getter
  wrapper无写误当成整个属性访问无写。
- 实现：Sol扩展initializer_value的独立receiver observation，旧link状态兼容；
  主代理在现有getter_returns添加check_property_no_memory_write消费者，按同TU
  唯一expression ID选取原始属性、fresh恢复和fresh getter检查，不信外部报告。
- 支持边界：唯一extern非TLS/nonreference/nonvolatile、无initializer对象；
  exact声明/使用类型一致，允许CUDADeviceAttr/WeakAttr但不由属性推断语义。
  raw PseudoObjectExpr以外的outer cast/enclosing body不在保证范围。
- 显式前提：receiver已初始化、生命周期有效，扩展遵循static-member求值规则；
  root及五个ID精确绑定，两个布尔必须is True，非空引用仍unverified。
  外部leaf域、ABI、无写及正常返回前提沿用，source/deploy始终false。
- 本地验证：make check 518项、make demo、54项真实Clang专项通过；包括真实引用
  别名/TLS/volatile/internal/call receiver拒绝、两个协议错绑定、stale root、
  缺ABI/错leaf、重复表达式及预算边界。Sol只读复核组合未发现错误放行路径。
- 固定TU声明诊断：artifacts/wb04-receiver-inspect-iYjgiX/report.json，
  receiver 0x248cf210同TU仅一处VarDecl，extern类型const __cuda_builtin_blockIdx_t，
  children仅CUDADeviceAttr/WeakAttr。这只是声明观察，不证明初始化或生存期。
- 标准参考： https://eel.is/c++draft/expr.ref 、 https://eel.is/c++draft/expr.context 。
  对象表达式仍求值；受限非volatile discarded glvalue没有lvalue-to-rvalue读取。
  MS-property扩展对应仍作为明确前提，不从标准文本自动推导编译器实现正确。
- 历史CI：d1c5285的run35737468910 success，不代表本轮提交CI。
- 完整TU执行：`PYTHONPATH=src python3 artifacts/wb04-property-effect-HqeldU/replay.py`，
  退出0；报告artifacts/wb04-property-effect-HqeldU/report.json，SHA256
  92e713888cc3613abf5c0b7e8b4417482fc2a82e7ce2b4382c0bdcde2091e548。
  同原AST 5b612a12a1955a3db65467d16fb69c9df7501f29d828403cae0a38b8995afa4f，
  400万节点预算，精确expression 0x7b148d1cfb58，四个实现文件前后hash一致。
  单属性条件checked；receiver/effect引用仍unverified，leaf非负int域和32位ABI
  沿用上一诊断协议，不声称实际host launch已满足。不是整个body无写证明。
- 没有执行：GPU、整核/整个loop无写检查、实际launch域恢复、候选生成或性能。
- 下一项：将真实循环体内所需属性调用逐一组合，并检查实际launch/坐标域；
  不应把本轮单表达式条件结论升级为vLLM整体已支持。
- 提交安排：验收后直接commit并推送当前分支，不PR；大型原始工件本地忽略。
