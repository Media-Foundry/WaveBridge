# HIP 外层数学调用与实参求值

2026-09-30，基线`04a1e72`，分支`wb03-source-ast`。
新增`scalar_call_effects.inspect_native_call`，复用既有直接callee绑定、受限
标量实参效果检查与native参数链检查；不消费旧成功报告或外部效果协议。

## 实际命令与输入

```bash
PYTHONPATH=src:. python3 -u -m experiments.softmax_call_audit \
  --native artifacts/wb-hip-native-20260927-01/native.json \
  --using-shadows --unary-float --unary-forwarding --outer-calls \
  --output-dir artifacts/wb-hip-native-outer-20260930-01
```

固定输入SHA256：`46ac52b1c672fadd0e5a66bb3ab380373e0cd69929713d96e7010f375a0cd63e`。
复用已采集真实HIP native envelope，未重新编译生产TU、未运行GPU。
驱动语法选点仅追最多32层直接单return路径，不是穷尽调用清单；不能将空
结果或全部选中项checked当成整个entry的调用覆盖或动态执行证明。

## 保证范围

父报告只连接精确外层call、实参求值和wrapper到精确builtin的参数结构。
实参的`argument_evaluation_no_memory_write_checked`与callee/whole-call效果
明确分开；后两者始终false。初始化、有效索引、存活和正常求值仍为前提。
builtin效果/正常返回、浮点结果、完整循环、最终机器码和部署未建立。
参数链失败时允许保留已检查的实参子结论，但父报告仍unknown。

## 回归与复核

新增5项真实native组合测试（其中包含多种源码变体），覆盖局部数组实参、
递增/赋值/嵌套调用、间接callee、错误leaf、坏wrapper与冲突ID。
父子native输入哈希及outer call/argument/policy哈希有一致性断言。
AST mutation负例明确作为fixture，不当成新的真实生产源码结果。
指针下标目前保持unknown；未为通过测试放宽标量表达式子集。

SDK23 native专项16项通过（0.373秒），匹配AOCC17插件专项16项通过
（0.363秒）。补充哈希/驱动配置断言后24项定向回归通过（0.374秒）。
全量1254项CPU测试通过（106.487秒，无跳过），make demo、diff通过。
全量中的unary/using专项使用SDK23，旧native专项使用AOCC17；不是全量
SDK23或远端CI验收。日志在`/tmp/wb-native-outer-{check,demo,aocc,targeted}.log`。

GPT-5.6 Sol只读复核未发现P1，建议明确选点非穷尽边界并补齐父子哈希
断言；本轮已落实文档和断言。默认外部scalar leaf协议入口未扩展保证。

## 重放结果

进程退出0，`observed`；输入、src实现及driver依赖哈希运行前后一致，结束后
再次与当前文件核对一致。报告
`artifacts/wb-hip-native-outer-20260930-01/report.json` SHA256：
`b9b982380d0eda950fb3c5dfe7d5256d72f0e4c08c3c90471b5e83333d582a95`。

| 外层语法call ID | wrapper路径 | 限定检查结果 |
| --- | --- | --- |
| `0x745c579bf7c0` | exp → expf → builtin_expf | checked |
| `0x745c579c0000` | exp → expf → builtin_expf | checked |
| `0x745c579c0f40` | exp → expf → builtin_expf | checked |
| `0x745c579c1780` | exp → expf → builtin_expf | checked |
| `0x745c579c2e50` | log → logf → builtin_logf | checked |

五处均独立重新检查实参和完整参数链；没有复用前一处call的通过结论。
它们是同一实例中的五个语法位置，不是五个kernel或动态执行次数。
全部父子输入哈希一致，callee/whole-call/source/deploy标记均false。
