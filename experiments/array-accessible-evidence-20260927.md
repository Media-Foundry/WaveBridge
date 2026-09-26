# shuffle wrapper与程序可访问存储保持

2026-09-27，wb03-source-ast，基线761c7a1；无GPU、无生产AST重采。

```bash
PYTHONPATH=src:. python3 experiments/softmax_array_effects.py \
  --native artifacts/wb-native-template-OqD1PQ/native.json \
  --output artifacts/wb-array-accessible-b7z7LN/replay.json \
  --use-scalar-operators --use-native-lifecycle --use-literal-defaults \
  --accessible-protocol experiments/softmax-accessible-leaf-protocol-20260927.json
```

协议文件SHA256：
`c9a085aa07bf43e2e3a9221dc92bce58b5237e9ddc4a1b9568ca454b1f065996`。
native文件SHA256仍为
`a59c12247f796fe2034ba03ecc43782f77ac3942496b18a140ceacbb24c7ff45`；
协议绑定的是规范化payload哈希
`1aeb23bc4c4bb7891060ac378c5405873b429451471a8c51e96bfed1781e880b`，
不是外层JSON文件的字节哈希。

## 新保证的范围

新callee checker不复用纯函数/no-memory-write标签。它精确检查float返回、
最多8个float/int/unsigned int标量形参的最多4层single-return wrapper，
每一层内嵌调用的实参从完整AST重新检查。重声明、递归、不支持的body、
副作用或不匹配声明均保持unknown。builtin必须匹配同次native记录的call、
decl、有序参数ID和编译器builtin身份，而不是靠名称前缀。

控制表达式检查复用scalar_expression_effects，显式允许受限const整数全局
literal读取以及同类型整数位操作；TLS、可变全局、引用或写入均拒绝。
这是无内存写入检查，不证明位移范围、算术有效性或返回值。

leaf保持程序可访问存储、所有到达实参上的有效参与/正常返回仍是外部前提。
协议引用上一轮的实际IR证据，但evidence_status=unverified、
external_leaf_effect_verified=false，不能将probe包装成完整production验证。
intrinsic的inaccessible-memory效果和convergence义务没有被删去。

callee报告明确排除外层实参。array组合必须继续扫描原CallExpr的全部孩子，
所以“callee通过”不能掩盖`global = ...`实参、未知默认值或其他写入。
额外未消费协议也拒绝。父级结论只在记录的完整前提下解释。

## 回归

GPT-5.6 Sol新增8项真实native回归并只读复核：多层wrapper、leaf身份与协议
错绑、内部写入/未知调用、outer实参排除边界、数组组合、unused协议、
常量控制位表达式及TLS/可变全局/赋值负例。定向8项通过，既有scalar19项
也通过。完整测试与demo日志保存在本轮目录。远端CI未核验。

完整make check：1113项通过，75.974秒，native启用、无跳过；make demo及
git diff --check通过。

## 固定真实工件结果

输出SHA256：
`f03be57e61f737b3840147de65d49b76ad807d1c1d25f5187e50e68f41d9958d`，
inputs_unchanged=true。两层wrapper 0x30d89288与0x2e2c7bf8均重新检查，
共8个内层实参无内存写入条件checked；最后一个表达式明确读取常量声明
0x2dc920b0和width形参0x2e2c7ad8，未省略位运算。

在该显式外部协议下，所选Max helper调用的status=checked、pending为空、
protected_storage_preserved=true，7处显式写入分类保持。这是callee、所有
外层实参、默认值、operator与trivial对象效果共同组合的条件结论，不是只
消费一个成功的leaf报告。被保护对象是同一caller的local_idx 0x30ddbeb0。

外部leaf效果仍未被自动证明，数组边界、参与、正常执行等前提仍保留；
source_program_checked/deployable=false。尚未把本检查接入initializer到
输出循环的完整历史保持：后续语句、其他归约调用及其他协议仍需fresh检查。
下一步应接回这条真实历史链，不再把本局部通过扩大成整核或跨波宽等价。
