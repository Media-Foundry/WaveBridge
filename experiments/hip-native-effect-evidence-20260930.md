# HIP 一元数学调用的条件效果敏感性重放

2026-09-30，基线`8d607ce`，分支`wb03-source-ast`。
本轮不认证设备math库无写入，只检查显式leaf前提如何组合到精确调用。

## 命令与冻结输入

```bash
PYTHONPATH=src:. python3 -u -m experiments.softmax_call_audit \
  --native artifacts/wb-hip-native-20260927-01/native.json \
  --using-shadows --unary-float --unary-forwarding --outer-calls \
  --assume-unary-effects \
  --output-dir artifacts/wb-hip-native-effect-20260930-01
```

输入SHA256：`46ac52b1c672fadd0e5a66bb3ab380373e0cd69929713d96e7010f375a0cd63e`。
不修改AST；不重新编译生产TU、不运行GPU，不读取旧成功报告。

驱动为语法选中的每个outer call记录现有leaf效果协议；协议精确绑定native
envelope、leaf call及callee ID。`evidence_reference`明确写作development
sensitivity assumption，`external_effects_verified=false`。外层检查器fresh
重建实参、参数链和leaf协议适用性，不以生成协议作为通过证据。

选点清单非穷尽，最多32层直接单return路径，不是动态执行次数或kernel数量。
`external_effect_protocols`按outer ID索引，仅是敏感性记录，不是完整协议
inventory；实际结果验收还要核对列表中outer ID无重复。结构结果与条件效果
结果分别保存：结构checked不能覆盖效果unknown。

## 实现与负例

`builtin_calls.check_call_no_memory_write`显式一元模式复用fresh
`inspect_native_call`和fresh builtin leaf效果检查，零参旧路径继续支持。
默认不开启一元/using支持；模式与协议绑定输入hash。条件结论仅是精确
call表达式的no_memory_write，且leaf假设必须覆盖实际可达的全部参数值。
初始化、存活、有效索引/算术等子检查前提保留，不认证FP值、环境或机器码。

`column_loops.recover_with_call_effects`接收显式选项；真实Clang源码正例可
在外部前提下恢复递推，带实参递增或循环变量写入的负例unknown。默认正例
也unknown，证明没有暗中扩大默认支持。这些是小型源码回归，不是完整生产
softmax循环验收；本轮实际生产重放只到精确call效果。

## 验收

1258项CPU测试通过（105.238秒，无跳过），make demo/diff通过。
新增native专项20项SDK23通过（1.107秒）；AOCC17匹配插件与driver专项
28项通过（1.066秒）。后补direct builtin、开关和结构/效果分离断言后，
SDK23定向28项通过（1.168秒）。全量采用新unary/using SDK23、旧native
AOCC17混合配置，不声称全量SDK23或远端CI通过。
日志：`/tmp/wb-native-effect-{check,demo,aocc,targeted}.log`。

GPT-5.6 Sol只读复核未发现阻断/P1；补充direct builtin及独立开关边界、
结构成功/效果失败的断言，明确驱动索引非穷尽。

## 真实重放结果

进程退出0，`observed`，输入/src/driver哈希运行前后一致，并在结束后与当前
文件再次核对一致。报告`artifacts/wb-hip-native-effect-20260930-01/report.json`
SHA256：`a8af8a027126343d9221d593efdd2a1e709b1ba1588d89ee129fcf21fa9f617b`。

同一实例的4处exp（`0x745c579bf7c0`、`0x745c579c0000`、`0x745c579c0f40`、
`0x745c579c1780`）和1处log（`0x745c579c2e50`）均为条件checked。
5个outer ID互异，协议映射与报告列表集合一致；逐项协议哈希、native
envelope及子检查绑定核对一致。外部效果verified/source/deploy均false。

这表明在声明的未验证前提下，现有结构/实参检查足以组合这些精确调用的
条件效果；不表明真实设备库无写入已经建立。实际生产loop工作检查尚未
接入这些选项，不能把本报告记作生产softmax循环通过。
补充断言后的AOCC17定向28项再次通过（1.169秒），日志
`/tmp/wb-native-effect-aocc-final.log`。
