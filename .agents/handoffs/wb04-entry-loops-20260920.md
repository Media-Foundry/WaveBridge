# 入口前缀循环上界交接

- 日期/分支/基线：2026-09-20，`wb03-source-ast`，`d17f0f9`。
- 用户约定：中文，直接commit及阶段性push，不创建PR、不自动合并master。
- 本轮：新增entry_loop_check，将fresh列域检查和归约链入口控制义务按唯一loop
  range、callee及call range绑定；不读取人工循环oracle。列区间checker在checked
  时提供max_iterations_per_thread及max_iterations，不改变其它状态语义。
- 分工：Sol实现次数摘要及小域计数回归，主代理实现组合/测试/真实验收；Sol再
  只读审查，确认没有将有限迭代结论反向用作可达性前提。
- 验证：`make check`，404项CPU测试通过；`git diff --check`通过。新增7项测试，
  覆盖idle线程、零列、精确绑定、缺失/重复域、上游失败短路、次数元数据不一致。
- 实际命令：`PYTHONPATH=src python3 artifacts/wb04-entry-loops-4ITPxL/check.py`。
  重跑线程起点、列域、归约链及入口循环组合，条件checked。前缀有1个列循环，
  列域[1,1023]、block256、stride256，线程0..254最多4次，线程255最多3次。
  两个前缀getter正常返回义务原样保留。所有src实现hash运行前后一致。
- 报告：`artifacts/wb04-entry-loops-4ITPxL/report.json`，SHA256
  `ebd8f0722994169d96a701680a7efe92130c82ad5a806dde58ce3f3c8bf290b6`。
  同目录有runner/thread报告；报告保存源/AST/ABI/绑定/实现/runner文件hash。
- 原AST：`artifacts/wb03-initializer-value-02/ast.json`，SHA256
  `b9392df45575e1c4bf818ef1bf982c1b0dd2b76e3905f9da0ed6dd05c772a70e`。
  ABI为examples/abi/storage-conditional.json；绑定为
  artifacts/wb04-thread-start-psY2gK/binding-final.json。大工件仅本地保存。
- 未执行：新HIP编译、GPU作业、性能实验、候选生成或整核等价验证。
- 边界：仅证明显式前提下的递推次数上界及末增量安全性。column_domain的到达
  循环前提继续保留，body正常完成是外部前提，不是已检查事实。不能据此声称
  helper可达、collective收敛或内存有效；participation/source/deploy不升级。
- 下一步：建立独立的前缀正常执行路径，明确getter正常返回协议与loop body有效性，
  避免复用本条件循环报告去证明它自身的到达前提。整体目标和G1仍未完成。
