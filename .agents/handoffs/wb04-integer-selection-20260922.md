# 动态整数选择交接

- 日期：2026-09-22；分支 `wb03-source-ast`，基线 `9d2e389`。用户要求中文回复、
  直接提交及阶段性推送，不创建 PR。前一提交远端 run35743161594 三任务 success。
- 文件：新增 `verification/integer_selection.py`，基于完整 TU 精确 ID 检查
  两个 const 内建整数引用参数的 minimum 函数及调用结果立即读取；函数名无语义。
  既有 `constructor_arguments` / `constructor_values` 门控没有改动。
- 协议：完整 root/表达式 ID、声明闭区间及 ABI 都绑定哈希。区间必须精确覆盖
  使用的变量/形参声明；比较两侧与真/假分支一一对应。仅支持最小子集，
  无上下文值域推测、通用调用解释器、指针别名或引用生命周期推导。
- 分工：GPT-5.6 Sol 实现独立 checker；主代理编写真实源码 fixture/测试、
  审查实现、运行全量验收及完整 TU 重放。
  二审后修复反向比较报告的硬编码位置，并增加 bare callee 类型、参数 ID 唯一性、
  conditional/call 类型及非内建转换目标门控；相应畸形 AST 负例已纳入。
- 实际验收：`make check` 545 项通过；`make demo` 通过；
  `PYTHONPATH=src python3 -m unittest discover -s tests -p '*clang*.py'`
  78 项通过。`PATH=/opt/rocm/llvm/bin:$PATH PYTHONPATH=src python3 -m unittest
  tests.test_integer_selection_clang` 8 项通过，无 skip。默认 AOCC Clang 17，
  后一项 ROCm Clang 23。`git diff --check` 通过。
- 保证边界：给定域和 ABI 下的立即读取 minimum 值区间及转换保持；不保证
  返回引用身份、外围 ExprWithCleanups、输入域来源、对象复制及 launch 前值保持。
  源有效性、对象/临时对象存活和选定函数正常返回是显式前提。
- 最终完整 TU 命令：`PYTHONPATH=src python3
  artifacts/wb04-integer-selection-FGW6dS/run.py
  artifacts/wb04-selection-final-1wvQWc/report.json`。
  报告 SHA-256 `bf0b08263aa1a0550c162830defd5937f05aaf4debd33485406d7c4c9b3d4a1e`。
  输入 AST 文件 SHA-256
  `5b612a12a1955a3db65467d16fb69c9df7501f29d828403cae0a38b8995afa4f`；
  root canonical hash `97da57a94da3614db2fb47dd9dfffedf135015512dbb75da015c2c3f04ccf433`。
  400 万节点预算；156.00 秒；三个实现文件前后哈希一致。
  原始表达式 `0x3b006cc8`、callee `0x3b0067a8`；显式诊断假设
  hidden_size `0x3b005a58` ∈ [1,4096]、int/unsigned int32 时结果条件 checked，
  输出 [1,1024] 且 IntegralCast 值保持。没有使用投影代替完整 TU。
  这是既有 development TU 的复验；不是独立 holdout 或 Tensor.size 域恢复。
  初版重放保留在 `artifacts/wb04-integer-selection-FGW6dS/report.json`，
  最终依据以上独立报告；中间一次重放因继续收紧门控而主动停止，未作验收依据。
- 未执行：GPU、性能、自动候选部署、新独立 holdout；WB-03 未完整验收。
- 下一步：将该值表达式与构造实参/字段按精确 AST 绑定，继续建立 hidden_size
  输入域来源和对象到 launch 的保持义务；不能直接将诊断区间当实际 launch 域。
