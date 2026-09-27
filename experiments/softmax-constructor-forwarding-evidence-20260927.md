# 构造实参到字段的条件符号关系

2026-09-27，基线 `553b551`，分支 `wb03-source-ast`。

`constructor_argument_effects.check_scalar_field_forwarding` fresh连接三个
原有检查：显式标量实参无写入、精确alias record/唯一构造类型绑定、构造体
与全部直接字段初始化的效果检查。它从**转换后的实参**开始建立字段相等，
不借用人工字段域，不把int操作数与unsigned转换结果混为一谈。

仅支持参数/字段双射，参数与实参类型相同，字段初始化仅含保持类型的
LValueToRValue/NoOp与括号。IntegralCast字段窄化不支持。字段交换按真实
参数位置输出关系，而不是假定x/y/z各自对应位置0/1/2。

## 重放命令

```bash
PYTHONPATH=src:. python3 experiments/softmax_launch_native.py \
  --native artifacts/wb-native-template-OqD1PQ/native.json \
  --output artifacts/wb-constructor-forwarding-check-giY75E/replay.json \
  --constructor-field-forwarding
```

会话49655正常结束，独立 `constructor_field_forwarding_check.status=checked`。
报告SHA256：`1a607d5167b4fd2412ae7c88a998d56dd93b9dd687f21348bef4ba5bac1b1d61`。
`inputs_unchanged=true`，结束后逐文件核对实现与driver依赖仍相同。

构造表达式 `0x30d69d08` 精确绑定构造声明 `0x2dcb8c78`、record `0x2dcb8758`。

| 字段ID | 参数ID | 位置 | 转换后实参ID |
| --- | --- | ---: | --- |
| `0x2dcb88f8` | `0x2dcb8a50` | 0 | `0x30d69c88` |
| `0x2dcb8960` | `0x2dcb8ad0` | 1 | `0x30d69cc8` |
| `0x2dcb89c8` | `0x2dcb8b50` | 2 | `0x30d69ce8` |

以上是在正常构造返回、有效AST和显式int32/unsigned32 ABI等条件下的符号
对应，不是字段数值域或合法dim3证明。来源仍是既有手工harness的CUDA
device-only sm80 AST，不是完整生产TU或新的GPU运行。

## 验证

GPT-5.6 Sol新增4项真实Clang回归与只读复核，主树专项4项通过（0.181秒）。
初次完整1192项通过（93.101秒，native启用、无跳过），demo/diff通过。
随后补强窄化测试：加入unsigned short完整ABI，确认构造效果子检查checked，
而组合层仍以 `field_not_bijective_nonconverting_parameter_forward` 拒绝。
最终验收日志为同目录 `check-final.log`，重放后未修改生产实现或driver。
最终完整1192项通过（91.997秒，native启用、无跳过）。

未建立的义务包括原始值到转换值保持、字段数值域、先前quotient关系在构造
求值点的数值实例化、除数非零、构造后对象历史、清理与实际启动语义。
对应字段和source/deploy继续为false。
