# 剩余softmax数学调用的精确参数转发

日期2026-09-27；基线daa3321；分支wb03-source-ast。

上一轮四处unknown：行149/152两个循环在同一std::exp调用处拒绝；行192/197
两个循环包含动态break。collective调用处于这些循环之间，不能将当前这些
循环首拒绝误记为collective问题，也不能用循环递推恢复率代替跨lane保证。

新checker只接受单float按值参数、float返回的单return直调free-function链，
逐层核对callee以及source/target ParmVarDecl ID。外部无body leaf由精确ID
选择，不按exp名称赋予数学语义。global/local替代、修改参数、算术/显式转换、
额外写入、递归、指针/引用和预算超限均拒绝。

## 固定工件回放

```bash
PYTHONPATH=src python3 -m experiments.softmax_scalar_forwarding \
  --native artifacts/wb-column-builtins-twz82w/native.json \
  --recovery artifacts/wb-column-builtins-twz82w/recovery.json \
  --output artifacts/wb-scalar-forwarding-PFKZhi/replay.json
```

输出必须不存在。输入分别固定SHA256：
`317b1a438bc13845cf76b5aa7461db4db2081b402c457a85c4160fdd7257c027`、
`4b209cf805ca46d40293a595b9d3c65a891a394e3a5111467c70f0e56b777ce7`。
driver按先前unknown_range选择唯一CallExpr，再选择其单return链；checker
从完整AST重新检查，不信任选择器提供的成功状态。

观察到链exp → expf → __nv_expf：

| caller → callee | source参数 → target参数 |
| --- | --- |
| 0x169866e8 → 0x166929b0 | 0x16986650 → 0x16692918 |
| 0x166929b0 → 0x165e5d40 | 0x16692918 → 0x165e5ca8 |

结果structure.status=checked，value_semantics/effect_semantics均not_established。
返回值、数学精度、外部leaf无写与正常返回、实际调用参数
`elements[i][it] - max_value[i]`的求值都没有被这条结构结论证明。

报告SHA256：`409b27d15538871fe849ffe981d716b4132586eed5e4eb34fe6347cdb397f7c2`。
报告记录src实现和driver/导入辅助模块哈希，前后输入稳定。未重采前端、未运行
GPU；旧4/8条件循环恢复未改变，更不是整核、性能或独立holdout结论。

GPT-5.6 Sol新增5项真实Clang回归，含重命名链、错误参数流/效果与32/33层
边界、AST预算；仅测试声明身份和结构，没有借用函数名模板推断预期关系。
