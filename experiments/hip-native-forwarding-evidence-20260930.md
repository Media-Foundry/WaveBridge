# HIP wrapper 到 native leaf 的精确参数转发

2026-09-30，基线`ea08716`。复用原scalar链检查，新增独立native入口；
不修改输入AST，不提供外部效果协议，不执行GPU。

## 实验入口

```bash
PYTHONPATH=src:. python3 -u -m experiments.softmax_call_audit \
  --native artifacts/wb-hip-native-20260927-01/native.json \
  --using-shadows --unary-float --unary-forwarding \
  --output-dir artifacts/wb-hip-native-forwarding-20260930-02
```

输入固定SHA256：`46ac52b1c672fadd0e5a66bb3ab380373e0cd69929713d96e7010f375a0cd63e`。
驱动沿实际直接引用/单return body选择路径，然后由独立入口重新检查完整
wrapper结构和每条参数边，不按函数名填写关系模板。语法清单中的外层call
仅作来源索引，不证明分支执行或外层实参求值安全。

## 范围

最终`artifacts/wb-hip-native-forwarding-20260930-02/report.json` SHA256：
`5be0249d702fbe8602e94daa827f7ff1a28c36d44e019b52478dc8a81209451e`。
退出0，observed，输入/src/driver依赖哈希前后一致。

| wrapper路径 | 精确起点 | 精确native终端call | 结果 |
| --- | --- | --- | --- |
| exp → expf → builtin_expf | `0x2054bf90` | `0x204e0f28` | checked |
| log → logf → builtin_logf | `0x2054eb08` | `0x204e7270` | checked |

两个路径各检查两层wrapper。exp来源索引包含4个语法外层call，log包含1个；
不将它们计成独立kernel或动态执行次数。child使用独立native链schema，
native envelope/call/policy哈希均被自身和父报告绑定。

检查从wrapper定义入口到精确builtin调用的参数转发，不是返回值数学性质。
终端既需native身份/实参结构成立，也需其读取的声明ID等于当前wrapper
形参ID。另一处同builtin调用、其它函数的同类型形参不能完成这条绑定。

外层实参、builtin效果/正常返回、浮点环境、源码到机器码对应和完整循环
仍未建立。两个子报告与父报告都不能据此签发GPU部署。

## 历史与复核

首版`artifacts/wb-hip-native-forwarding-20260930-01/report.json`保留，SHA256
`2384ed3a3bc2e9617e7ff1c18f66713322b31c397ec08cea2824a04a845d57c5`。
两条wrapper路径已checked；GPT-5.6 Sol复核未发现P1，但指出嵌套child使用旧
schema/hash导致单独消费时终端边界不够清楚。后续版本绑定child的native
call/envelope/policy，并给父报告显式列出假设和限制；首版不删除、不当成
修订后报告的验收证据。

## 验收

17项SDK23 native/普通scalar专项通过（0.250秒）；11项native专项在AOCC17
匹配插件上通过（0.148秒）。新增测试覆盖精确两层链、同builtin另一处call、
foreign形参、wrapper写入/实参变化，以及child/parent终端哈希一致。
foreign形参是明确标注的原AST mutation，不是新的真实源程序。

最终1249项CPU回归通过（98.512秒，无跳过），make demo和diff通过。全量中
新unary/using专项使用SDK23，既有native专项使用AOCC17匹配插件；不称全量
SDK23验收。日志`/tmp/wb-native-forwarding-final-check.log`、
`/tmp/wb-native-forwarding-demo.log`、`/tmp/wb-native-forwarding-aocc.log`。
结束后独立核对当前src/driver哈希以及父子终端哈希一致。未核验远端CI。
