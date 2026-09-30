# 交接：同次query的源码运行时守卫

- 日期/分支/基线：2026-09-30，wb03-source-ast，79d975d；开始时工作树干净。
- 用户约定：中文、持续推进，直接commit并周期push当前分支，不创建PR。
- 实现：normal_return_guard.check_local_equality；query initializer/minimum/
  quotient的query_guard_id组合。guard紧邻target、plain local!=literal、
  direct无实参noreturn失败支路；先fresh检查初始化到guard的历史/控制。
  shared literal和terminal callee leaf仅全字段一致时支持，调用/guard仍唯一。
- 候选：experiments/softmax_query_guard.py，固定3个历史输入hash，只在forward
  插入if(width!=32) abort，新目录输出；不改kernel/launch或backward，不覆盖旧输入。
  这是fail-stop候选，不是fallback/native64适配或全输入等价变换。
- 验证：1366项全测141.901秒无跳过；/tmp/wb-source-guard-check.log。
  Clang23/17各20项39.223/38.874秒，生成器3项、demo/diff通过；Sol两轮无阻断。
  首轮共享callee不支持导致unknown/专项失败，修正后重新跑过全部验收。
- 新候选：artifacts/wb-hip-query-guard-candidate-20260930-01/native.json，SHA256
  df7d0b37e1d7ca16977f6d133285705d004a655e880b87b635148a373816e8b5。
  collected/inputs_stable true；完成后再次验证历史三个输入hash完全不变。
- 重放：artifacts/wb-hip-source-guard-20260930-01/report.json，SHA256
  771f1a83bcc2c30b524f38a4245034bae47cd6558db99f5becb72285d0dae378。
  全部fresh子链checked，源码guard域[32,32]、商[4,4]，source-guard安全true，
  external-domain安全false。完整新ID、命令、协议边界见实验实录。
- 没执行：链接后的程序/GPU、性能评测。新native采集是前端编译，不是设备正确性。
- 前提：API输出/枚举转换、noreturn实际链接、有效C++执行/生命周期等未自动验证；
  source/deploy false。移除的仅是额外query数值域假设，不能泛化所有API调用。
- 提交/推送：主agent完成验收后直接提交同步；大AST/报告仍本地保存。
- 下一项：将守卫后已知query/minimum/quotient值连接到真实候选launch字段及
  后续值保持，核对kernel/launch一致性。不要绕过其余门槛直接跑优化或部署。
