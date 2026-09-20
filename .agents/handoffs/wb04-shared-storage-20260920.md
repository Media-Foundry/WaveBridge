# 同AST共享数组容量组合交接

- 日期/分支/基线：2026-09-20，`wb03-source-ast`，`8da6916`。
- 约定：中文回复，直接commit，阶段性push，不建PR、不合并master。
- 上轮为实质进展：共享整数关系已验收并推送；本轮衔接对应数组及分配容量。
- 实现：shared_storage_check fresh运行shared_index_check及归约链/launch恢复，
  核对kernel→helper、共享形参ID和width/block，再调用独立shared_capacity。
  不复用旧容量报告；保存输入及独立sizeof协议hash、三类嵌套证据。
- 分工：主代理实现及真实验收；GPT-5.6 Sol编写组合负例并只读审查，未发现实质
  问题；主代理补静态extent回归。动态和静态路径共7项新增测试。
- 验证：`make check`，388项CPU测试通过；`git diff --check`通过。
- 真实命令：`PYTHONPATH=src python3 artifacts/wb04-shared-storage-QGyPZ1/check.py`。
  fresh线程起点→helper坐标→共享下标→数组/容量组合checked，block256/width32，
  8个float槽需32字节，launch提供128字节；实现hash运行前后一致。
- 报告：`artifacts/wb04-shared-storage-QGyPZ1/report.json`，SHA256
  `5ec511e2dfb2f758665d33e14833d7b1e28b237121f1932961dde6b50c386b39`。
  同目录有runner/thread报告，主报告保存实现/runner/ABI/绑定工件hash。
- 固定AST：`artifacts/wb03-initializer-value-02/ast.json`，SHA256
  `b9392df45575e1c4bf818ef1bf982c1b0dd2b76e3905f9da0ed6dd05c772a70e`。
  ABI为examples/abi/storage-conditional.json，绑定为
  artifacts/wb04-thread-start-psY2gK/binding-final.json；大工件仅本地保存。
- 未执行：新编译、GPU作业、性能实验、自动候选或整核等价检查。
- 局限：单数组偏移0及无其它动态分配仍是前提，未自动证明布局独占；仍依赖
  实际launch/ABI/API、真实上游证据和可信前端。没有证明别名、同步、参与或
  存储值正确，不签发source_program_checked/deployable。
- 下一步：明确绑定barrier/shuffle外部语义与线程参与，连接两阶段贡献关系。
  G1差异、留出谱系和自动GPU闭环依然未完成，整体目标保持进行中。
