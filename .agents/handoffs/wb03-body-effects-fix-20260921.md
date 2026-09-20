# 循环体副作用P1修复

- 日期/分支/基线：2026-09-21，wb03-source-ast，6f947ec；中文、直接commit并push，
  不创建PR。用户审阅固定8778335，本轮在更新基线复现相同问题。
- 修复：现有column_loops新增最小存储目标分类与body节点白名单，不新增通用
  别名分析模块。支持直接非保护标量/简单数组下标写入，拒绝复杂左值及未知
  效果；引用逃逸、取址、调用保守拒绝。header/body状态分开，column_domain_check
  强制两种body保持证据。数组存储仍需memory_no_alias和有效源程序前提。
- 真实复现：固定6f947ec原module文本在同一Clang AST重放，static_cast<int&>、
  C-style引用转换、逗号左值、asm均recovered；修复后均unknown，正例不变。
  命令：`PYTHONPATH=src python3 artifacts/wb03-effects-fix-sl2zdX/check.py`，退出0。
  报告SHA256 `c5833015090c633f7fb23086d969c6e1042c43bc26778ccd9349966a14a86dd2`，
  同目录保存fixture AST、runner、报告；实现hash前后一致。原HIP AST两循环
  step256仍recovered。旧报告只保留历史证据，不可替代修复后的重新恢复。
- 测试：Sol编写两组真实Clang回归和fixture，主代理补直接写入及状态门控。
  `make check`最终451项通过，3.936秒；本机Clang为AMD AOCC 17.0.6。
  真实column_domain_check内部不mock recover_columns/inspect_launch/recover_guards；
  正例checked、直接写入与四种绕过unknown。线程报告是明确的手工测试前提，
  未证明线程getter、实际GPU launch或完整程序。CPU witness编译执行确认引用
  cast变体在N768下仅写512列，数学coverage checker未改。
- CI：新增ubuntu24.04/Clang18 source regression任务，记录完整compiler版本；
  这是工作流实现，本轮尚未取得远端任务通过证据。
- 状态同步：research/differential-cases.md记录人工Polygeist O1九输入通过，
  保留O0失败及static shared、OCML/OCKL、wrapper、AS5、wave库补丁边界；
  不再以“未进入GPU”概括当前状态。corpus区分原始TU、手工HIP standalone、
  CUDA adapter。没有新增GPU/性能结果，也没有改变数值协议。
- 未完成：独立开发谱系holdout；完整生产TU；include内容/实际wrapper后端/
  resource-dir/SDK依赖绑定。用户提供sandbox复现包不在本地，本轮使用自行
  创建的真实源码fixture复现，不声称已运行该附件脚本。
- 下一步按审阅次序：冻结当前支持子集，选择许可和固定版本清楚的独立谱系
  真实kernel，记录未经逐函数模板的覆盖/拒绝；再补最小预处理或依赖输入
  工件绑定。不得将这些合成测试算holdout，WB-03整体保持未验收。
