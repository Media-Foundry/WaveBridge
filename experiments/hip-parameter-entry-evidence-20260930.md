# HIP host 参数入口保持

基线：`ce79026`，分支 `wb03-source-ast`。本轮不执行 GPU。

## 新检查的范围

`verification/parameter_entry.py` 从同一完整 AST 的精确函数、plain-int 参数及
目标 DeclStmt 出发，对外部给定有限整数域的**每一个值**检查入口前缀。
上限 4096 个域值，另有 AST 与执行步数预算；这不是随机抽样测试。
仅解释整数/布尔只读条件、短路逻辑、compound、if 和单次 do。
实际执行到调用、声明、写入、别名或未知控制流即 unknown，不推断其无副作用。
未执行的分支可跳过；报告分支清单只是“至少一个域值跳过”的并集。

结论止于目标声明的首次入口，目标自身不求值。入口域是外部前提，未与真实
调用输入绑定；不是 launch 域、最终 GPU 程序或源/目标等价证明。

## 固定 HIP 重放

输入：`artifacts/wb-hip-native-20260927-01/native.json`，SHA-256：
`46ac52b1c672fadd0e5a66bb3ab380373e0cd69929713d96e7010f375a0cd63e`。

```bash
PYTHONPATH=src:. python3 -m experiments.softmax_launch_native \
  --profile hip \
  --native artifacts/wb-hip-native-20260927-01/native.json \
  --output artifacts/wb-hip-parameter-entry-20260930-01/report.json \
  --host-dimensions --power-input-domain 65 128
```

驱动从 fresh host operand/call 绑定中选取 owner、实参参数与指数声明语句，
不以函数名字或断言宏名字签发语义。相同区间分别作为函数入口和调用读取点的
诊断前提，两个检查并列报告；不把新检查偷偷升级成已验证的调用输入协议。

实际源码入口是断言宏展开的 do/if，其后有零长度返回分支。此例应通过条件
求值排除 abort 路径，而不是给 abort 函数补写“纯函数”协议。

## 验收与剩余义务

真实 Clang fixture 覆盖合法条件前缀、直接修改、using 引用别名、可达调用、
重复 do、仅部分域可达的修改、域扩展后的返回/调用、预算与身份冲突。
独立 Sol 只读复核未发现参数保持错误放行；其报告措辞建议已落实。

仍需把独立的参数入口保持和调用/移位检查
正式组合，绑定外部输入协议，再处理设备 API 返回域与后续 host 值历史。
不将本轮有限域检查称为通用控制流/别名分析，也不宣布 WB-03 完整验收。

## 实际结果

报告 SHA-256：`72e586912fe4d6a1ef8d5a6ddad2d668f242c57095d72ff70ed362866e211ed6`。
`inputs_unchanged=true`，入口检查条件 checked：完整枚举64个域值，1536次节点
求值，参数保持到目标声明首次入口，结果域仍为[65,128]。独立 initialized-shift
仍checked，但`entry_domain_verified`、`call_domain_established`、整核与部署
标记均false。没有执行GPU、没有新数值或性能结果。

5项新增真实Clang测试通过；完整`make check`为1295项、100.722秒、无跳过。
完整日志：`/tmp/wb-parameter-entry-check.log`。运行环境沿用SDK23 visibility、
unary/using插件与AOCC17 native插件的显式组合；不是全部测试统一使用Clang23。
`make demo`及`git diff --check`通过。新增源码与驱动在实际重放期间保持冻结。
