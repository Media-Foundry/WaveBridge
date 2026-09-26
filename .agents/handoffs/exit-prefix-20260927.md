# 退出guard前缀值交接

- 日期/分支/基线：2026-09-27，wb03-source-ast，8012aa3；开工干净。
- 用户约定：中文，验收后直接commit/push当前分支，无PR，不合并master。
- 完成：在loop_exit_guards中新增check_prefix_values；fresh分区＋初始化无写
  检查，有序prefix_value DAG，self/later引用拒绝；原分区入口保持不变。
- GPT-5.6 Sol新增4项真实Clang测试并复核；同DeclStmt多变量暂不支持。
- 实际验证：make check，1039项/69.163秒（匹配native插件，无跳过）；demo/diff通过。
- 实录：experiments/exit-prefix-evidence-20260927.md；工件及日志在
  artifacts/wb-exit-prefix-YYjQh5/。两个guard checked，inputs_unchanged=true。
- 没有执行：GPU、生产AST重采、远端CI核验。
- 保证范围：prefix后的typed值关系及条件无已有对象写入；不检查header/work、
  数值域、溢出、跨迭代稳定性或完整覆盖。循环仍6/8、整体unknown。
- 提交：本轮文件直接commit/push，无用户改动混入。
- 下一步：连接原始loop header、精确induction和guard DAG中的声明，检查
  work保持性和外部输入域后推导截断迭代域；不得忽略退出迭代的prefix计算。
- 阻塞：本轮无；整核与跨波宽适配仍未建立。
