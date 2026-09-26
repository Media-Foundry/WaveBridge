# 完整调用点的条件无写入检查

基线074fefa，日期2026-09-27，分支wb03-source-ast。

新增check_call_no_memory_write从完整native AST选择一个CallExpr，检查完整
callee及参数结构，再fresh检查builtin或wrapper链。wrapper内部边和调用点
共用严格direct-callee结构函数，不从callee名称推断效果。

## 固定CUDA工件回放

输入native报告：artifacts/wb-native-builtins-JR99CL/probe-final.json，SHA256
`ae5cf2a142e6790859a0d4340caa677dae1fc78609ba40f5d0d743f0f7f6aa82`。
复用上一轮回放中显式标为演示假设的协议，未复用其成功结论；协议来源报告：
artifacts/wb-builtin-wrappers-3uFzg5/replay.json，SHA256
`e0ed1da39372d3e7de004dfaf2ae5eae698d470bb25b30c07be6d91386ed7b3a`。
两份文件在回放前均核对固定哈希。

| 位置 | 所选CallExpr | dispatch | 结果 |
| --- | --- | --- | --- |
| wb_huge | 0x229463d8 | direct_builtin | checked，conditional |
| wb_nan | 0x22946628 | direct_builtin | checked，conditional |
| wb_limits_huge | 0x22946958 | direct_zero_argument_wrapper | checked，conditional |
| wb_limits_nan | 0x22946c48 | direct_zero_argument_wrapper | checked，conditional |

输出artifacts/wb-builtin-callsite-fHWEOs/replay.json，SHA256
`6be9b2a181b63b87cb58ceed838271fad744a2b375d8400af66720b017ae1a73`。
本轮builtin_calls.py SHA256：
`c553a90cec535235228dbddf7e898988abf3111f6d6f0a462800cc9564f368be`。

没有验证外部无写假设，也没有把IR观察当成源码保证；所有结论仍只在前提下
成立，不建立返回值/FP语义、循环保持性或部署。没有新GPU和生产TU重采。

## 真实负例与范围

GPT-5.6 Sol新增3项真实Clang回归，正例覆盖free/static/direct builtin；
负例含`(counter++, target)()`、`make_receiver().static_target()`、函数指针及
unknown external。先检查目标wrapper单独checked，再检查带副作用的调用点
unknown，避免把函数体性质误当成整个调用求值性质。主代理补3项fixture覆盖
隐藏callee children、错误cast、额外实参、重复ID和预算。

MemberExpr即使receiver看起来无副作用也暂不支持；没有默认忽略其求值。
本接口不检查CallExpr以外的父级表达式/语句，不能由其中一个调用通过推出
整个循环或函数无写。核心column_loops调用门控尚未改变。
