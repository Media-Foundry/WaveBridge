# builtin 条件效果组合交接

- 日期/分支/基线：2026-09-27，wb03-source-ast，7acc2d5。
- 用户约定：中文，验收后直接 commit/push 当前分支，不创建 PR。
- 实现：现有 builtin_calls.py 新增 check_no_memory_write，fresh结构检查再
  连接精确 envelope/call/callee 绑定的外部假设，不复用调用者旧报告。
- 协议：builtin-leaf-effect-assumption/v1；参考 docs/contracts.md 示例及
  compiler/verification/README.md。无写实现假设不覆盖参数求值。
- 实际测试：新增3项fixture和3项真实Clang；GPT-5.6 Sol实现真实回归并复核。
  主代理加强副作用负例，使用真实envelope哈希而非占位值以隔离拒绝原因；
  `nanf((counter++, ""))` 保持 fresh_builtin_structure_not_checked。
- 完整验收：992 项/66.713秒/native插件启用/无跳过；最终Clang专项9项通过，
  demo/diff通过。日志 artifacts/wb-builtin-effects-b4dEG6/。
- 没有执行：GPU、生产前端重采、远端 CI；不是独立谱系或整核验收。
- 局限：external_leaf_effect_verified=false，value_semantics未建立；条件
  no_memory_write仅所选CallExpr，不代表纯度或包围函数/循环保持性。
- 下一步：将这种条件调用效果接入严格受限的单返回wrapper检查，检查完整
  wrapper及其callee/参数求值后再考虑循环集成；不能直接以名称开放调用。
- 提交状态：本轮验收后统一提交推送。
