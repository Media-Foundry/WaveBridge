# 嵌套退出循环的工作依赖保持性

2026-09-27，wb03-source-ast，基线e6f480c。本轮无GPU、无生产AST重采。

```bash
PYTHONPATH=src python3 -m experiments.softmax_exit_guards \
  --native artifacts/wb-column-builtins-twz82w/native.json \
  --recovery artifacts/wb-loop-calls-SIr4BJ/all-calls.json \
  --work-preservation --static-branches --nested-loops --int-bits 32 \
  --output artifacts/wb-nested-work-4pjRnM/replay.json
```

输入与上一轮静态分支回放相同，native SHA256为
`317b1a438bc13845cf76b5aa7461db4db2081b402c457a85c4160fdd7257c027`，
recovery SHA256为
`31a6570762225ea247f24b799be28ebd51f3dab13e562e32cccb8e305d764f67`。
旧recovery仅提供固定选择与显式外部协议，不输入通过结论；所有检查重新执行。

新增显式use_nested_loops模式，独立schema
`loop-exit-work-preservation-with-nested-loops/v1`。内层逐次fresh连接原始
header/prefix/guard；原始初始化、条件、增量检查祖先依赖保持，prefix、完整
guard和work检查祖先与内层依赖的并集。即使最终break，prefix也不能省略。
内层调用按精确ID重新核验，未消费协议仍阻止父项成功。默认模式不变。

该结论只涉及受保护声明的条件存储保持。它不证明完整迭代域、整数溢出、
终止、覆盖、FP值、源程序有效性或GPU部署。外部leaf效果、无别名和无异步
干扰等前提仍未验证。历史6/8循环恢复不自动提升，不是新blind holdout。

实际验证命令：

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_loop_exit*'
WB_NATIVE_CAPTURE_PLUGIN=/home/husrcf/Code/ProtBind/wavebridge/artifacts/wb-native-builtins-JR99CL/libwavebridge_capture_plugin.so \
WB_NATIVE_CAPTURE_COMPILER=/opt/AMD/aocc-compiler-5.1.0/bin/clang++ \
make check
make demo
git diff --check
```

专项30项通过（4.418秒）；完整1058项通过（73.388秒，native启用，无跳过）；
demo/diff通过。日志位于artifacts/wb-nested-work-4pjRnM/。
GPT-5.6 Sol新增5项真实Clang回归并只读复核，覆盖leading/trailing内层正例、
对外层induction/guard的写入及引用别名、header/prefix副作用、未知调用、
while和静态分支组合。远端CI未核验。

固定AST回放完成，inputs_unchanged=true，输出SHA256：
`efd0be4e9b7e48897df772d1b65635b87baaf7a78dbb215b402016c9c699a931`。
两项work均条件checked，unused协议均为空，完整调用0x19550c18均重新检查。
外层嵌套报告绑定loop 0x19551220及原始路径[4,2,1]，header对祖先保持、body
对合并依赖保持均conditional。祖先为WARP_BATCH、local_batches、i；合并集合
再包含element_count、WARP_SIZE、WARP_ITERATIONS、local_idx、it。
内层单独检查没有新增nested节点。两项source_program_checked及
full_iteration_domain_established均为false，未将历史恢复状态升级。
