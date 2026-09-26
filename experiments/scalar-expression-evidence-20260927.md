# 标量实参求值效果回放

2026-09-27，基线adce149，分支wb03-source-ast。无GPU执行，无生产AST重采。

使用上一轮同一native TU和固定调用选点，独立检查实参
`elements[i][it] - max_value[i]`；没有用参数转发结构的成功代替实参求值检查。

```bash
PYTHONPATH=src python3 -m experiments.softmax_scalar_expression \
  --native artifacts/wb-column-builtins-twz82w/native.json \
  --forwarding artifacts/wb-scalar-forwarding-PFKZhi/replay.json \
  --output artifacts/wb-scalar-expression-bNET54/replay.json
```

输出checked、inputs_unchanged=true。结果SHA256：
`7ff09a072546445061e6ac0692c18f569e6e83e632891ad215ea8d471fc70f73`。
报告记录native/选点工件哈希、实现前后哈希、driver依赖及完整条件检查。
工件仅本地保存，不随Git上传；driver固定输入哈希以防跨AST混用ID。

范围是单个表达式的显式内存写入，不是exp或其外部leaf实现的效果证明。
初始化、存活、下标/算术有效性、正常返回和无异步效果仍是外部前提。
没有建立值语义、浮点数值等价、完整循环或GPU部署保证。
原softmax循环接受状态未改变；该案例仍是已暴露development输入，不是blind holdout。
