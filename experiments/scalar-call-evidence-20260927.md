# 完整单标量调用条件效果

2026-09-27，wb03-source-ast，基线0c03e50。本轮无GPU、无生产AST重采。

```bash
PYTHONPATH=src python3 -m experiments.softmax_scalar_call \
  --native artifacts/wb-column-builtins-twz82w/native.json \
  --forwarding artifacts/wb-scalar-forwarding-PFKZhi/replay.json \
  --output artifacts/wb-scalar-call-0M9lz4/replay.json
```

固定输入内的外层`exp(elements[i][it] - max_value[i])`调用条件checked，
inputs_unchanged=true。输出SHA256：
`3a4dd37815d11bccca809a006f964526c16c4a1a25c219a8b60565aaf9167b42`。
报告保存源码checker实现前后哈希、driver依赖、输入工件哈希与完整子报告。
工件本地保存，不随Git上传。旧报告仅提供选点ID；转发链/参数效果重新检查。

driver明确注入**未验证的敏感性假设**：精确外部leaf对该调用全部可达参数值
不写内存、有效且正常返回。这不是工具链性质的证据，也不是从函数名推导的
纯度结论。实参求值不由leaf假设覆盖，包含修改时仍unknown。

独立checker成功仅描述所选完整调用。参数初始化/存活/索引/算术有效性仍为
前提；不证明FP环境、返回值、循环、整核或部署。默认循环恢复未改变。
此PyTorch输入仍是development，不是独立blind holdout。

匹配native插件下make check：1024项通过，67.822秒，无跳过；make demo和
git diff --check通过。日志在artifacts/wb-scalar-call-0M9lz4/。
GPT-5.6 Sol新增5项真实Clang组合测试并只读复核；远端CI未核验。
