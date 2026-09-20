# 归约入口控制义务交接

- 日期/分支/基线：2026-09-20，`wb03-source-ast`，`01d5f77`。
- 约定：中文、直接commit、验收后push，不建PR或自动合并master。
- 进展：上一轮为验收并推送的容量组合。本轮补上局部贡献恢复跳过前缀的证据缺口，
  不将“能识别归约”当作“所有线程能到达归约”。
- 实现：analysis/entry_control定位精确顶层目标调用，保留入口至首次调用前缀的
  调用正常返回和循环终止义务；拒绝早退、条件调用、跳转、嵌套循环、短路、汇编
  及未知节点。reduction_chain增加子报告，source.py实现hash清单包含新模块。
- 分工：主代理实现与真实验收，GPT-5.6 Sol编写8项回归并只读审查。主代理再加
  真实Clang早退反例及source报告hash回归。`make check`共397项通过。
- 命令：`PYTHONPATH=src python3 artifacts/wb03-entry-control-ocHj3Y/check.py`。
  原始HIP AST重建chain与entry_control均recovered，两个getter精确ID分别为
  `0x2d2b9db8`、`0x2d2b8c08`，另有一个For终止义务。没有解除这些义务。
- 最终报告：`artifacts/wb03-entry-control-ocHj3Y/report.json`，SHA256
  `f9286cf2d5ce56653a24ce7d214abeaad75ea520915a49568a1afc57affd3722`。
  运行前后src实现hash一致，runner及实现hash保存在报告内，大工件不入Git。
- 输入AST：`artifacts/wb03-initializer-value-02/ast.json`，SHA256
  `b9392df45575e1c4bf818ef1bf982c1b0dd2b76e3905f9da0ed6dd05c772a70e`。
- 未执行：新HIP编译、GPU作业、性能/候选实验。真实Clang编译只用于CPU回归。
- 保证边界：recovered不是checked；participation仍not_established，source/deploy
  均false。循环或调用可能不终止，算术/内存有效性也未证明。仅描述首次目标调用，
  不分析后缀回跳和多次调用同步序列。MemberExpr仅按ID记录，不赋予语义。
- 下一步：用同AST列域检查解除前缀循环终止义务，连接getter调用正常返回条件，
  然后建立有明确外部API前提的首次helper到达检查；不能提前宣称barrier收敛。
