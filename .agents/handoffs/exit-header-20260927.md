# 循环头与退出条件连接交接

- 日期/分支/基线：2026-09-27，wb03-source-ast，7bd39e7；开工干净。
- 约定：中文、直接commit/push当前分支，无PR、不合并master。
- 完成：column_loops.observe_header及loop_exit_guards.check_header_connection，
  不修改AST/删除break，默认recover不变；独立schema阻止误用header观察。
- GPT-5.6 Sol新增5项真实Clang回归及只读复核。
- 验证：make check，1044项/69.607秒（匹配native插件，无跳过）；demo/diff通过。
- 固定回放：softmax两处header/guard连接checked、inputs_unchanged=true，
  原header分别0..<2和0..<4、step1；详见experiments/exit-header-evidence-20260927.md。
  工件/日志artifacts/wb-exit-header-rwbFtF/。
- 没有执行：GPU、生产AST重采、远端CI核验。
- 保证：仅原header观察与同源induction依赖，body修改仍可能有checked连接；
  work保持、guard单调性/稳定性、overflow和完整访问域均未建立。仍6/8、unknown。
- 提交：本轮文件直接commit/push，无用户改动混入。
- 下一步：在显式受保护声明集合上检查work效果（含嵌套loop与所有分支），
  不把callee局部checked直接替代whole-work；建立后才连接输入域/溢出与截断访问。
- 阻塞：本轮无；整核/跨波宽/GPU闭环仍未建立。
