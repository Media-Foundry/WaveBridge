# 前缀 getter 函数体返回交接

- 日期/分支/基线：2026-09-20，`wb03-source-ast`，`46b5a74`。
- 用户约定：中文，直接commit、阶段性push，不建PR、不合并master。
- 本轮进展：在既有无环single-return getter检查成功报告中显式记录条件正常返回；
  entry_call_check fresh恢复入口义务，按root/kernel及startID协议逐项验证body。
  缺契约保留部分证据、整体unknown；值保持rejected不升级为不终止反例。
- 分工：Sol补getter completion及负例，主代理实现组合、测试、真实验收；Sol只读
  审查组合通过。`make check`409项CPU测试通过，`git diff --check`通过。
- 真实命令：`PYTHONPATH=src python3 artifacts/wb04-entry-calls-7LiwN4/check.py`。
  从原AST重跑thread_start检查，从其derived_leaf_domain构造仅local-id的显式
  getter协议；没有构造block-id域。local-id start `0x2d2b8c08` body条件checked，
  block-id start `0x2d2b9db8` 因contract missing为unknown，整体unknown。
- 报告：`artifacts/wb04-entry-calls-7LiwN4/report.json`，SHA256
  `ec95ed149bf8cf2c463bb18d3132362cf6132d22867147f00b29f15f9cd67149`。
  同目录有protocol.json、thread-report.json与runner；src实现hash前后一致。
- 输入AST：`artifacts/wb03-initializer-value-02/ast.json`，SHA256
  `b9392df45575e1c4bf818ef1bf982c1b0dd2b76e3905f9da0ed6dd05c772a70e`。
  integer ABI来自examples/abi/storage-conditional.json；坐标绑定沿用
  artifacts/wb04-thread-start-psY2gK/binding-final.json。大工件不入Git。
- 未执行：新HIP编译、GPU作业、性能、候选变换、整核等价。
- 局限：外部叶正常返回及值域均为显式假设，未用运行测试证明；completion只覆盖
  getter body，不能证明callsite receiver/参数求值、循环body、helper可达或收敛。
  participation/source/deploy均未升级。新的unknown是具体缺失协议，不是工具故障。
- 下一步：核实block-id精确外部调用与grid域协议的来源；建立该绑定后再处理调用点
  求值和前缀内存有效性，不通过随意填写上界把整体unknown改成checked。
