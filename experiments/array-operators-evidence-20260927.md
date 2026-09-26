# 从实际方法体检查数组helper中的标量operator

2026-09-27，wb03-source-ast，基线d8b4850。无GPU、无生产AST重采。

```bash
PYTHONPATH=src:. python3 experiments/softmax_array_effects.py \
  --native artifacts/wb-column-builtins-twz82w/native.json \
  --output artifacts/wb-array-operators-aDT0Ht/replay.json \
  --use-scalar-operators
```

固定native SHA256：
`317b1a438bc13845cf76b5aa7461db4db2081b402c457a85c4160fdd7257c027`。

## 方法与边界

本轮复用scalar_expression_effects检查器，扩展bool字面量、同类型int/float
比较、prvalue与标量lvalue条件表达式。条件和真假分支全部递归检查，不因
某个分支“看起来不会执行”而跳过。引用别名、写入和调用仍保持unknown。
无内存写入不等于精确值、浮点环境、边界或机器码等价。

array_call_effects新增显式use_scalar_operators模式，默认行为保留。只处理
精确const float(float,float) operator()，receiver必须为helper局部对象
的直接引用及加const的NoOp转换，方法非virtual/static/variadic，两个参数
为float，函数体只有一个ReturnStmt。返回表达式从同次完整AST重新检查，
读取仅限两个参数；不能由函数名Max或const修饰符推断无写入。

方法体检查完成后，实际调用的receiver和实参仍由外围写入范围遍历处理。
例如实参中写全局变量仍阻断整体检查。对象初始化及生命周期独立保留，
本入口不接入历史保持，也不提升loop入口域。

## 固定工件的实测结果

输出SHA256：
`740589dd0feee5547b2f6fa55f4806c8fb199ca8d2c5187f9c5ec69355094aed`；
inputs_unchanged=true。operator调用0x19538fa0精确绑定方法0x194f2b28，
receiver 0x19538580。返回表达式的无内存写入检查条件checked，只读取两个
float形参0x194f2998与0x194f2a10。没有借用人工成功报告。

7处显式写入分类保持，pending从5项减少为4项：对象生命周期、构造表达式、
WARP_SHFL_XOR调用及默认实参。父级仍unknown，保护对象保持和部署均false。
下一步检查构造/生命周期及shuffle/defaultarg，不将方法体通过代替整次调用。

新增5项真实Clang条件表达式回归由GPT-5.6 Sol实现并复核；另增加2项数组
组合回归，覆盖方法体通过而生命周期未解除、方法写入/未知调用不放行、
实参写入不被方法体的局部通过掩盖。定向12项测试全部通过。

完整测试和演示原始日志位于`artifacts/wb-array-operators-aDT0Ht/`。
原生插件启用的make check：1090项通过，73.695秒，无跳过；make demo与
git diff --check通过。
远端CI未核验。本轮结果不构成新GPU、跨波宽或性能证据。
