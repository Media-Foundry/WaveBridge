# 完整调用点交接

- 日期/分支/基线：2026-09-27，wb03-source-ast，074fefa。
- 用户约定：中文，验收后直接commit/push，不创建PR。
- 完成：check_call_no_memory_write精确选点、完整callee/参数结构检查并fresh
  调用builtin/wrapper检查；抽取共享direct-wrapper-target避免两处规则漂移。
- 回放：两个直接builtin和两个numeric_limits调用点conditional checked，
  沿用演示用外部协议；输入/输出哈希见experiments/builtin-callsite-evidence-20260927.md。
- 测试：新增3项fixture和GPT-5.6 Sol实现的3项真实Clang；wrapper单独成功仍
  不能覆盖comma callee或副作用receiver，function pointer/unknown继续拒绝。
- 完整验收：1006项/66.906秒/native插件启用/无跳过，demo/diff通过；
  日志 artifacts/wb-builtin-callsite-fHWEOs/check.log 与demo.log。
- 未执行：GPU、生产前端重采、远端CI；没有整核或独立谱系验收。
- 边界：完整所选CallExpr但不是其父表达式/语句；无返回值、FP、纯度或机器码
  保证；external_leaf_effect_verified=false，核心列循环门控不变。
- 下一步：在同次native AST和精确协议绑定下，将此调用点效果接入受限循环
  保持性；仍须遍历其它body节点，不能让子调用成功覆盖父级写入/未知效果。
- 提交状态：本轮验收后提交推送。
