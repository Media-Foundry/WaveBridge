# 交接

- 日期、分支、基线：2026-09-27，wb03-source-ast，7b215ef。
- 目标：连接ideal-real模型与实际保存reference输出；中文回复，直接commit/push。
- 完成：rmsnorm_roundoff.ideal_intervals以整数sqrt和精确Fraction包围具体
  binary32行的理想输出；不调用浮点sqrt。reference_interval_audit绑定历史
  input/expected/protocol/reference哈希，逐点组合reference误差与fresh条件模型界。
- epsilon：reference原始调用来自runner的Python binary64字面量1e-5；报告
  JSON可round-trip重建。GPU源码固定1e-5f，为不同的binary32值，两者分开处理。
- 实跑：旧工件wb02-20260926T154202Z-d8e8d1的3×777、2331保存点；三行
  reference绝对误差上界均<5.8e-8，四组mode/width模型的精确实数容限余量均正。
  未运行GPU或reference生成算法；不是native64运行结果，也不是全域reference证明。
- 工件：artifacts/wb-reference-interval-jvPDdv/；report SHA256
  9502dfe7d2451c95f4a2e6d1ef052619605e95723bef42a2a8b1cd65ba519153。
- 验证：7项新增测试；完整876项CPU测试通过，64.784秒，匹配native插件启用，
  无跳过；make demo/git diff --check通过。proof-writer补齐条件组合证明，
  GPT-5.6 Sol独立只读复核无阻断问题。
- 限制：不证明expected确由保存reference.py生成；只证明这些精确保存值
  相对理想区间的关系。模型与实际source/compiler/runtime/FP律及host comparator
  舍入仍未闭合；numeric_contract_checked/deployable=false，原协议未变。
- 提交状态：随本轮提交并推送当前分支，无PR，无master合并。
- 下一步：结合已明确ISA与reference边界接实际编译/运行门槛；有限点证据
  不能替代独立谱系或完整适配链验收。
