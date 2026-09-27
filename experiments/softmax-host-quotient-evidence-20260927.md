# host minimum 到 warps_per_block 初始化

2026-09-27，基线 `1e4fa4d`。本轮处理实际 `threads_per_block / warp_size`，
不把除法的关系恢复写成域或安全性证明。

## 实现边界

`integer_selection.check_minimum_quotient` 先fresh重建minimum更新及其到目标
DeclStmt入口的历史，再解析唯一automatic int initializer。分母必须精确读取
同一个受保护声明；分子必须读取唯一const int声明，并由现有常量求值器从
源码重新计算，所有常量依赖逐ID核对。只接受非负且可表示的int常量。

输出关系为 `truncate_toward_zero(K / min(before_operands))`。分子非负排除
INT_MIN/-1溢出，但**不排除除零**：`division_safety_established=false`，
`denominator_nonzero_at_division`显式列为未解除义务。没有输入或生成手工32域，
没有建立正维度、完整lane家族、quotient后续保持或构造转换。

GPT-5.6 Sol编写6项真实Clang测试并只读复核，覆盖正常嵌套block、精确K与
snapshot关系，以及改运算/分母、别名、多声明、static、窄类型、bool、负K、
IntegralCast、隐藏节点和身份冲突。主代理复跑6项通过（0.183秒）。

## 重放

```bash
PYTHONPATH=src:. python3 -m experiments.softmax_launch_native \
  --native artifacts/wb-native-template-OqD1PQ/native.json \
  --output artifacts/wb-host-quotient-check-KtfTwO/replay.json --host-minimum-quotient
```

日志和验收结果位于 `artifacts/wb-host-quotient-check-KtfTwO/`。本次无GPU执行。
冻结后的完整1174项通过（92.325秒，native启用、无跳过），demo/diff通过。

## 真实结果

原会话6442正常结束，`host_minimum_quotient_check.status=checked`，
`inputs_unchanged=true`，完成后逐文件实现与driver依赖哈希一致。
报告SHA256：`d7d1d830fe8e39e74c7a425ca682a2c46a48b22231a0341e141ae410f19f781c`。

warps_per_block声明为`0x30d696c0`，除法表达式`0x30d697e0`，分母warp_size
为`0x30d691d8`。分子threads_per_block声明`0x30d695e8`从源码求得128，
不是把实验配置中的128输入checker。条件关系为
`trunc_toward_zero(128 / min(before_next_power_of_two,before_warp_size))`。

报告仍保留除数非零义务，division_safety、operand_domains、quotient后续
history、source_program_checked、deployable全部false。本结果没有消除
此前构造字段的selection_domain_missing，也不是合法launch的验收结果。
