# 初始化到最终输出循环入口的条件保持检查

2026-09-27，wb03-source-ast，基线d354fb4；无GPU、无生产AST重采。

```bash
PYTHONPATH=src python3 -m experiments.softmax_initializer \
  --native artifacts/wb-column-builtins-twz82w/native.json \
  --protocol experiments/softmax-initializer-protocol-20260927.json \
  --target-statement 0x19551298 \
  --call-protocols artifacts/wb-loop-calls-SIr4BJ/all-calls.json \
  --output artifacts/wb-initializer-history-6QT7HZ/replay.json
```

固定native SHA256：
`317b1a438bc13845cf76b5aa7461db4db2081b402c457a85c4160fdd7257c027`；
初始化leaf协议SHA256：
`56e4d92bae9457348061f413666c21cfdb3fda15bbea4ed1da7d0e508c0ac169`；
既有调用协议工件SHA256：
`31a6570762225ea247f24b799be28ebd51f3dab13e562e32cccb8e305d764f67`。
driver传入旧工件的显式调用协议，不使用其成功报告；每个实际遇到的调用
重新检查。未消费协议仍会阻止最终成功，不因来自旧工件而自动获准。

本入口重新检查local_idx初始化，并按相同函数体的结构索引绑定到较晚目标。
中间所有语句及标准ForStmt的init/condition/increment/body都要检查其对
local_idx存储的效果；不是只扫描变量名出现次数。静态分支来自同次AST，
unknown不能当false。全函数goto/label拒绝，以防词法顺序不能代表目标入口。
目标循环body及后续代码不在“首次入口前”范围；这不证明目标可达或循环终止。

实际验证：

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_initializer_history_clang.py' -v
WB_NATIVE_CAPTURE_PLUGIN=/home/husrcf/Code/ProtBind/wavebridge/artifacts/wb-native-builtins-JR99CL/libwavebridge_capture_plugin.so \
WB_NATIVE_CAPTURE_COMPILER=/opt/AMD/aocc-compiler-5.1.0/bin/clang++ \
make check
make demo
git diff --check
```

新增5项真实Clang回归通过（0.277秒），GPT-5.6 Sol负责测试及独立复核。
覆盖中间普通loop与只读使用、目标body/之后写入不影响入口结论、直接/别名/
header写入、未知调用、错误先后与scope、静态false、goto/label和预算。
最初带计数unroll正例被既有helper拒绝，改用受支持的无参pragma并保留
带计数hint负例；没有为让测试通过放宽共享helper。远端CI未核验。

完整1078项测试通过（73.984秒，native启用，无跳过），demo/diff通过。
固定回放inputs_unchanged=true，输出SHA256：
`2f02e319de38a0fed3e5f3e3528c22815bd0f88fbca8a96d9e95a41bf0abad71`。
结果unknown：call_effect_not_checked，调用0x1954ab18，上游header第145行
offset6378..6434，即warp_reduce<acc_t,WARP_BATCH,WARP_SIZE,Max>(max_value)。
函数0x194e0d80内声明索引7、目标索引20，已通过中间索引8..15共8条顶层
语句，索引16为上述未完成调用。完整builtin调用0x19548398 fresh checked。
后续语句和最终unused协议门槛尚未完成，不将局部成功升级为入口域保持。

该helper实际更新传入数组，不能通过声称它“全局无写入”来消除unknown。
下一步需建立真实写入范围、实参与形参绑定及与local_idx存储的不重叠，
或继续保留unknown。当前没有把初始化域替代旧loop-entry外部区间。
