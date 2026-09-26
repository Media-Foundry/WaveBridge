# 原始循环头与退出guard的同源连接

2026-09-27，wb03-source-ast，基线7bd39e7。无GPU、无生产AST重采。

```bash
PYTHONPATH=src python3 -m experiments.softmax_exit_guards \
  --native artifacts/wb-column-builtins-twz82w/native.json \
  --recovery artifacts/wb-loop-calls-SIr4BJ/all-calls.json \
  --header-connection --int-bits 32 \
  --output artifacts/wb-exit-header-rwbFtF/replay.json
```

observe_header复用原header解析且不修改AST、不删除break；header声明与常量
依赖必须精确绑定。check_header_connection重新检查prefix值关系，沿guard
可达DAG寻找同一induction声明，未使用的prefix读取不算连接。
int_bits=32是本次显式外部ABI假设，不是本轮硬件探测结果。

固定回放两个连接均checked，inputs_unchanged=true。结果SHA256：
`18ea26e84b06d24b86f3568e4e8c7a5a550272fbe428c4bc18a1a3710d5b319a`。
外层start=0、bound=2、step=1，induction 0x1954f2c8直接出现在guard operand[0]；
内层start=0、bound=4、step=1，induction 0x1954fd80出现在prefix定义
0x1954ff28的operand[1,0]，该定义再被guard引用。bound是本次固定模板的原header
常量，不是提前退出后的有效bound。ID仅在该固定TU内有效。

本入口只建立header结构与guard依赖身份。即使body会修改induction，也可能
观察到header并连接guard；真实Clang边界测试明确保留body/work/stability
未建立标记。这个结果不能替代完整recurrence、单调性或有效访问域检查。

完整1044项测试通过（69.607秒，匹配native插件，无跳过），demo/diff通过；
日志位于同一artifact目录。GPT-5.6 Sol新增5项真实Clang回归并复核。
远端CI未核验；保持历史6/8循环恢复、整体unknown，不产生GPU或holdout结论。
