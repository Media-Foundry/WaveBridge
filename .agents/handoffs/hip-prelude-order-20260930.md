# 交接：前置 false-condition do 的结构顺序

- 日期/分支/基线：2026-09-30，wb03-source-ast，ad40282，起始干净。
- 用户约定：中文，持续推进真实适配链，直接commit/周期push，不创建PR。
- 实现：_source_order检查全函数控制流后，精确验证false-condition do与
  source在共同Compound的分叉兄弟顺序；记录preceding_false_do_wrappers。
  不跳过do body，不放宽goto/continue/case归属、唯一性或动态条件限制。
- 原AST证据：仅一个外层前置DoStmt，源声明在后续If内，switch在源scope内。
  精确ID、命令、输入/实现/结果hash见experiments/hip-prelude-order-20260930.md。
- 回归：Clang17对象专项50项通过，Clang23新增两项通过；原完整Clang23
  捕获兼容性缺口仍保留。Sol只读复核无阻断，最终全测结果见实录。
- 边界：顺序是静态词法结构，不证明body无效果、动态必达、初始化完成、
  历史值保持或GPU配置。新前置do可能返回或影响全局，不因此排除动态义务。
- 未执行：没有重新编译或运行HIP/GPU；专项会执行既有小型CPU语义程序。
- 下一项：消费完整新结构报告的各子状态，fresh绑定初始化、各复制点历史、
  其它参数/调用效果和生命周期；不要只看父级checked。
- 提交/推送：主agent结束验收后同步当前分支；大原始工件留artifacts。
- 阻塞：无外部阻塞，剩余是语义组合与验证工作。
- 最终结果：1378项全测182.912秒通过；真实22次复制的source_order与前序
  cleanup观察均checked，前置do/source分支位置0/1。前序wrapper清单为空
  不是全部动态析构不存在；初始化仍null，历史与deploy未建立。
