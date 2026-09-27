# minimum 更新到 threads 声明入口

2026-09-27，基线 `07561f8`。本轮连接前一项实际minimum赋值与同一个block内
后续threads声明的首次入口；不以源变量初始化值代替更新后的值。

## 检查边界

`integer_selection.check_minimum_to_statement` 不接收旧成功报告，fresh重建
单次更新关系；要求两个端点属于同一个CompoundStmt且顺序正确，再逐条检查
中间语句。允许共同block在外层else内部，但不推断该分支实际执行。
全函数扫描目标变量的存储用途，包含array_filler；引用/地址逃逸、其他写入、
不透明中间调用与不支持控制流保守拒绝。更新前两个操作数以快照解释，不假设
它们在更新后也保持原值。后续写入即使不影响首次入口，当前也保守拒绝。

通过只建立目标语句入口的`history_preserved_to_use`。`target_statement_checked`
仍为false：目标内部实参求值、构造/调用、字段域及复制历史均未因此建立。
对象有效、已初始化、正常到达和无异步/非局部干扰等前提保留。

## 真实重放命令

```bash
PYTHONPATH=src:. python3 -m experiments.softmax_launch_native \
  --native artifacts/wb-native-template-OqD1PQ/native.json \
  --output artifacts/wb-host-history-check-7kISBN/replay.json --host-minimum-history
```

GPT-5.6 Sol负责真实Clang负例与只读复核。测试和原始结果在
`artifacts/wb-host-history-check-7kISBN/`。无GPU执行或数值结论升级。
冻结测试后，完整1168项通过（91.701秒，native启用、无跳过），专项7项复跑
通过（0.188秒），`make demo`和`git diff --check`通过。

## 实际结果

真实重放checked，`history_preserved_to_use=true`、`target_statement_checked=false`。
报告SHA256：`b626983dec4fe30e91ea9deb19d0c4a641b731efe79f252819ef9b370e1d5e40`。
`inputs_unchanged=true`，原会话77784正常结束；结束后逐文件核对实现与driver
依赖哈希一致。这里读取的是host_minimum_history_check，不是仅复述launch状态。

共同block `0x30d7b918`，minimum赋值位于child 3，threads声明
`0x30d69d50`位于child 9。child 4–8五条中间语句均通过保护检查，全函数记录
5个目标变量引用。到声明入口时，warp_size仍等于更新前两个操作数的minimum。
没有因此把next_power_of_two、API返回值或warps_per_block恢复成具体数值。

下一步需检查真实构造参数读取与独立warps_per_block值来源；再连接API、log2
与shift的合法域及路径。入口保持不能替代构造参数求值效果或对象复制前历史。
