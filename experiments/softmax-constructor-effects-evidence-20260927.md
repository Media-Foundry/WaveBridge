# 真实构造显式实参的独立效果检查

2026-09-27，基线 `3bc684a`，分支 `wb03-source-ast`。

新增 `constructor_argument_effects.check_scalar_evaluations`，从唯一
CXXConstructExpr重新取得完整显式实参列表，逐项调用标量无写入检查，
不调用构造值检查器，也不接受人工字段域。原有值检查入口保持不变。

标量检查新增默认关闭的 `allow_int_to_unsigned`，仅接收内建隐式
int→unsigned int转换，递归检查操作数效果。直接纯IntegerLiteral可在
模板实例中共享相同ID，但全部内容必须一致；其他表达式和声明仍要求唯一。
报告哈希绑定效果选项。写入、调用、引用、volatile、其他类型转换、默认
实参、冲突身份与预算不足不放行。转换值保持不在本检查范围内。

## 命令与结果

```bash
PYTHONPATH=src python3 -m unittest tests.test_constructor_scalar_evaluations_clang tests.test_scalar_int_to_unsigned_clang -v
WB_NATIVE_CAPTURE_PLUGIN=artifacts/wb-native-template-OqD1PQ/libwavebridge_capture_plugin.so \
WB_NATIVE_CAPTURE_COMPILER=/opt/AMD/aocc-compiler-5.1.0/bin/clang++ make check
make demo
git diff --check
PYTHONPATH=src:. python3 experiments/softmax_launch_native.py \
  --native artifacts/wb-native-template-OqD1PQ/native.json \
  --output artifacts/wb-constructor-effects-check-5vaMo2/replay.json \
  --constructor-argument-effects
```

9项专项通过（0.114秒）；完整1188项通过（92.975秒，无跳过），demo/diff通过。
原始测试日志、demo输出与重放报告位于上述本地artifacts目录，默认不入Git。
重放会话3511正常退出，报告SHA256：
`9bb4cff0e80675ceec035913acd9fcf899d845e230b56aab71f8f2737e5feeab`。

独立子报告 `constructor_argument_effects_check.status=checked`，不是仅凭
顶层launch绑定状态推断。构造 `0x30d69d08` 的三个实参
`0x30d69c88`、`0x30d69cc8`、`0x30d69ce8` 分别checked，
`all_arguments_no_memory_write=true`。根哈希：
`7fc29b3984296fefb0534cec735a2b40e8b89e453530613112990e00a4b92970`。
`inputs_unchanged=true`，重放结束后再次核对全部实现与driver依赖哈希一致。

## 保证范围

仍以有效AST、已初始化且存活对象、定义良好的运算与正常完成为条件。
此结果不检查构造体、分配/清理、精确构造声明绑定、字段值、转换值保持、
实参历史到字段的组合、除数非零、launch合法性或GPU执行。
对应字段以及 `source_program_checked`、`deployable` 均为false。
输入是既有手工harness下的CUDA device-only sm80 AST，不是完整生产TU，
不再是盲测holdout，也不是本机W7900的新运行结果。

下一步应独立建立数值域/API依据及构造字段连接；不能用无写入结论替代它们。
