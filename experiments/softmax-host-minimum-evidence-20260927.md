# softmax host 的实际 minimum 更新

2026-09-27，基线 `a08c32f`。上一轮具体模板实例绑定通过，构造值来源仍
unknown。本轮处理实际 `warp_size` 的一次可变赋值，而非把初始化值当作
后来仍保持的值。实现复用 `integer_selection.py`，未增加通用解释器模块。

## 保证与测试

新入口 `check_local_minimum_update` 从精确声明、比较方向、分支、类型及写入
目标建立单步关系 `after_target=min(before_operand0,before_operand1)`。
没有外部值域输入，不填入32；不调用旧初始化保持器来证明本来就修改了的变量。
限定普通函数内直接 CompoundStmt 语句，int 自动变量或按值参数；引用、volatile、
隐式变型、间接写入、调用、换分支、隐藏效果和歧义身份不能通过。
结论条件于到达该赋值、对象有效且已初始化、执行期间无异步修改。

GPT-5.6 Sol 提供7项真实Clang测试并只读复核，包含lvalue/prvalue及局部变量正例，
以及别名/调用/分支/目标/共享ID/隐藏子节点等负例。完整日志、demo与真实重放
位于 `artifacts/wb-host-minimum-check-0CnKXh/`。
完整1161项通过（91.558秒，native启用、无跳过），冻结后的7项专项再跑通过
（0.087秒）；`make demo`、`git diff --check`通过。

## 真实重放

```bash
PYTHONPATH=src:. python3 -m experiments.softmax_launch_native \
  --native artifacts/wb-native-template-OqD1PQ/native.json \
  --output artifacts/wb-host-minimum-check-0CnKXh/replay.json --host-minimum-update
```

原执行会话19153正常结束，`host_minimum_update_check.status=checked`，
`inputs_unchanged=true`，结束后核对逐文件实现及driver依赖哈希一致。
报告SHA256：`5b52af8914453247c8674826e69a1e3a282b59c6b96aa05d06c085f2355a535e`。

- 函数实例：`0x30a41828`。
- 实际赋值：`0x30d69470`。
- 写入目标：warp_size `0x30d691d8`。
- 更新前两个操作数：next_power_of_two `0x30d69090`、warp_size `0x30d691d8`。

即 `warp_size_after=min(next_power_of_two_before,warp_size_before)`，不是
`warp_size=32`。操作数域、到构造点的历史、launch尺寸和线程参与均未建立。
旧对象构造的 `selection_domain_missing` 没有被本结果自动消除。

真实代码位于 `softmax_elements==0` 早退对应的else块中；先前还有log2求值、
左移与warp_size API调用。后续需独立绑定这些来源、路径和执行时域，然后
处理warps_per_block除法与到dim3构造点的保持；不能把片段关系当作完整host分析。
本次未执行GPU，source_program_checked、deployable始终false。
