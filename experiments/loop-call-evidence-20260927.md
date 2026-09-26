# 条件标量调用接入循环恢复

2026-09-27，wb03-source-ast，基线df3abd9；无GPU、无生产AST重采。
新recover_with_call_effects允许混合builtin和scalar外部效果协议，fresh检查
完整调用；共享旧循环体/嵌套保护，但使用独立父子schema，旧入口不放宽。

```bash
PYTHONPATH=src python3 -m experiments.softmax_call_effects \
  --native artifacts/wb-column-builtins-twz82w/native.json \
  --builtin artifacts/wb-column-builtins-twz82w/recovery.json \
  --scalar artifacts/wb-scalar-call-0M9lz4/replay.json \
  --output artifacts/wb-loop-calls-SIr4BJ/replay.json
```

单scalar调用回放：4个调用子检查checked，unused为空，整体仍unknown；
循环节点仍4 recovered/4 unknown。两处循环拒绝点前移至offset6897的下一处
exp调用；两处输出循环仍在上游194/208行的break拒绝。局部call成功没有
错误升级整个循环。输出SHA256：
`7e78ec2aaad918f72b314e64cdf7a5306a3833eeff50b60f97f7caf306ab0f90`，
inputs_unchanged=true。节点计数含嵌套父/子，不是独立kernel覆盖率。

追加`--all-same-wrapper`选择同entry内精确相同callee声明的调用点，并为每个
点显式重绑定同样**未验证**的leaf前提。选择依据声明ID，不使用函数名；恢复器
仍逐个重查callee、wrapper和argument，不消费旧成功报告或忽略分支。

全同wrapper调用回放使用上述命令加`--all-same-wrapper`，output换成
`artifacts/wb-loop-calls-SIr4BJ/all-calls.json`。结果：7项协议（3 builtin、
4 scalar）全部fresh checked、unused为空，6 recovered/2 unknown，父报告
仍unknown。剩余拒绝仅为194/208行的动态break，没有因此删除或忽略这些控制流。
输出SHA256：`31a6570762225ea247f24b799be28ebd51f3dab13e562e32cccb8e305d764f67`，
inputs_unchanged=true。全调用选点driver另经GPT-5.6 Sol只读复核。

外部leaf、实参初始化/存活/索引/算术有效性及源有效性仍为前提；没有浮点值、
整核或GPU部署保证，不能把该development回放称为独立留出验证。
完整1028项测试通过；最终driver定稿后重跑69.421秒（匹配native插件，无跳过），
demo/diff通过，日志check-final.log保留。
GPT-5.6 Sol新增4项真实Clang组合回归并复核；远端CI未核验。
