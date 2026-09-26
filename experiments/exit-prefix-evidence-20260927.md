# 退出guard的前缀值连接

2026-09-27，wb03-source-ast，基线8012aa3。无GPU、无生产AST重采。

```bash
PYTHONPATH=src python3 -m experiments.softmax_exit_guards \
  --native artifacts/wb-column-builtins-twz82w/native.json \
  --recovery artifacts/wb-loop-calls-SIr4BJ/all-calls.json \
  --prefix-values --output artifacts/wb-exit-prefix-YYjQh5/replay.json
```

两个guard均fresh checked，inputs_unchanged=true；输出SHA256：
`ed96cfd9c0699fda6989863447ccd19e30242525823ffa1203042c8157b3b0bf`。
报告绑定输入工件、checker实现前后哈希、driver及辅助脚本哈希。

外层prefix为空，guard保存`i >= local_batches`的精确声明读取。
内层新增局部`element_index`（0x1954ff28）的值定义为有序typed AST：
`local_idx + (it * WARP_SIZE)`；guard保存该prefix_value与element_count的`<`
比较。local_idx/it/WARP_SIZE对应0x19546950/0x1954fd80/0x195459e8，
element_count为0x194e0b80；所有ID仅属于固定native TU，不能跨采集复用。

在源有效、无异步效果及算术定义等前提下，受支持prefix仅初始化新的普通
自动int对象，不修改已有对象；这不是工作分支或完整loop保持性的结论。
运算DAG保留加乘顺序，没有把C++ int解释为无界整数。WARP_SIZE数值、header、
跨迭代稳定性和溢出域未在本入口证明，不能直接推导有效bound或完整覆盖。
prefix在退出迭代同样求值。历史6/8循环恢复不升级，整体仍unknown。

完整1039项测试通过（69.163秒，匹配native插件，无跳过），demo/diff通过；
日志在同一artifact目录。GPT-5.6 Sol新增4项真实Clang回归并复核，覆盖纯声明
链、空prefix与赋值/自增/引用/static/TLS/volatile/调用/自读取等拒绝边界。
远端CI未核验；该案例仍development，不是blind holdout或GPU部署结果。
