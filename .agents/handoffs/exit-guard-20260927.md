# 提前退出结构交接

- 日期/分支/基线：2026-09-27，wb03-source-ast，b305043；开工干净。
- 用户约定：中文、直接commit/push当前分支，无PR、不合并master。
- 完成：loop_exit_guards、7项Clang/fixture边界回归、softmax_exit_guards固定
  回放及范围文档。GPT-5.6 Sol负责测试与复核。
- 实际验证：make check，1035项/69.179秒（匹配native插件，无跳过）；demo/diff通过。
- 真实回放两项结构checked、inputs_unchanged=true，路径/命令/哈希见
  experiments/exit-guard-evidence-20260927.md；工件artifacts/wb-exit-guards-hO8EFa/。
- 原失败：共享BreakStmt的全局ID唯一性检查unknown；保留replay.json。两Stmt
  各12处，改以唯一loop相对child-path绑定结构语句；guard/operand仍精确唯一。
- 没有执行：GPU、生产TU重采、远端CI核验。
- 范围：仅退出分区和guard操作数条件无写；不检查prefix/work效果、header、
  guard值或稳定性/有效bound/coverage。历史6/8恢复不提升。
- 提交：本轮文件直接commit/push，无用户改动混入。
- 下一步：将精确退出结构连接到header和guard值来源，证明prefix不改写循环
  状态与bound；推导截断访问域前必须保留break迭代的prefix求值与整数溢出义务。
- 阻塞：本轮无；不能把结构checked当作整核或跨波宽适配。
