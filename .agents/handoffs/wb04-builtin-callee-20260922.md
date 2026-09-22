# 交接：精确 builtin callee 转换

- 日期、分支、基线：2026-09-22，wb03-source-ast，932fab8；中文回复，直接 commit/push。
- 目标：解除完整 vLLM TU getter 的具体 BuiltinFnToFnPtr 障碍，不放开任意 builtin。
- 实现：Sol 修改现有 getter_returns，仅在直接 callee 支持零参、唯一精确外部叶、
  BuiltinAttr 与受限函数签名一致的该转换；call_edges 记录 cast_kind。
  主代理核验官方语义并添加真实 CUDA device-only 回归，无 toolkit 或 GPU 依赖。
- 语义参考：LLVM 17 OperationKinds.def 的 callee-only 约束：
  https://github.com/llvm/llvm-project/blob/llvmorg-17.0.6/clang/include/clang/AST/OperationKinds.def#L320-L322
  真实 AOCC17 JSON cast 为 `int (*)() noexcept`，child 为 `<builtin fn type>`；
  不照搬其它分析模块关于 cast 结果类型的描述，不推断函数指针间接调用支持。
- 验证：make check 509 项、make demo、Clang 专项49项通过。普通 getter路径不收紧；
  缺builtin证据、错ID、nonleaf、签名/category错配、嵌套及不透明callee仍unknown。
  真实CUDA正例以显式域/ABI/effect协议检查，body写入/调用unknown；负数域到unsigned
  返回仍rejected，缺effect协议仍unknown。
- 历史CI：932fab8 的 run35736704376 success；不代表本轮新提交CI。
- 完整TU重放：`PYTHONPATH=src python3 artifacts/wb04-builtin-callee-4GTh1i/replay.py`，
  正常退出0，报告 `artifacts/wb04-builtin-callee-4GTh1i/report.json` SHA256
  bca258957d636c431b7351d3c0175bec74ffecb926ea982867b12140bde425ad。
  原完整AST SHA256 5b612a12a1955a3db65467d16fb69c9df7501f29d828403cae0a38b8995afa4f，
  400万扫描预算，未投影AST。返回域及wrapper条件无写均checked，外部effect引用
  仍unverified。三个检查实现文件前后hash一致，getter_returns为
  e5661b0223454b20c1ddc05b179fde9e9a0bff1a4b7195f34fc9ba17d284bf57。
  诊断复用上一固定报告的显式协议：非负int域[0,2147483647]与32位ABI；
  不声称这个域已由实际host launch恢复，不升级整个vLLM案例状态。
- 保证边界：BuiltinAttr只确认语法表示，不提供无写、坐标或终止保证。外部叶
  实现、ABI、非负返回域和正常返回仍是明确前提；receiver、launch和body未组合。
- 没有执行：GPU、自动候选变换、整核验证、性能或新holdout验收。
- 下一项：exact receiver 求值及真实 launch 数值域连接，随后组合循环体义务。
- 提交安排：本文件随验收后的实现直接提交推送，无PR；原始大AST保持本地忽略。
