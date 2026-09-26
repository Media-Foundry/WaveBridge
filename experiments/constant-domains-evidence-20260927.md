# 从同次源码声明恢复常量输入域

2026-09-27，分支wb03-source-ast，基线ee5c646；无GPU、无生产AST重采。

```bash
PYTHONPATH=src python3 -m experiments.softmax_exit_guards \
  --native artifacts/wb-column-builtins-twz82w/native.json \
  --recovery artifacts/wb-loop-calls-SIr4BJ/all-calls.json \
  --work-preservation --static-branches --nested-loops --source-constants \
  --iteration-domains experiments/softmax-exit-external-domains-20260927.json \
  --int-bits 32 --output artifacts/wb-constant-domains-dSNJ9F/replay.json
```

固定native SHA256：
`317b1a438bc13845cf76b5aa7461db4db2081b402c457a85c4160fdd7257c027`；
旧recovery SHA256：
`31a6570762225ea247f24b799be28ebd51f3dab13e562e32cccb8e305d764f67`；
新外部域文件SHA256：
`b764ba10b48c0095b9337e372ca89eed88e3924f9b876507dc29bb0de273923b`。

本轮去掉旧示例域里手填的WARP_SIZE；显式常量模式从相同TU按声明ID重新
求值const int及依赖链，要求声明和全部已消费依赖唯一。已推导常量不得由
外部范围覆盖或重复提供，失败保持unknown。无法求值的动态const只有在
精确外部范围仍提供时才可能继续，这个范围不会被记成源码已推导。

余下local_batches [0,2]、element_count [0,128]、local_idx [0,31]仍为外部
示例前提，并非生产完整输入域。特别是源码local_batches = batch_size -
first_batch只进行上界裁剪，不能仅凭该源码声称其下界为0；完整范围还需要
实际launch及算术有效性证据。local_idx的threadIdx.x来源与转换也尚未在
本入口连接，因此不是线程坐标/launch范围已验收。

实际验证：

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_loop_exit_constant_domains_clang.py' -v
WB_NATIVE_CAPTURE_PLUGIN=/home/husrcf/Code/ProtBind/wavebridge/artifacts/wb-native-builtins-JR99CL/libwavebridge_capture_plugin.so \
WB_NATIVE_CAPTURE_COMPILER=/opt/AMD/aocc-compiler-5.1.0/bin/clang++ \
make check
make demo
git diff --check
```

新增5项真实Clang回归通过（0.297秒）；GPT-5.6 Sol实现测试并独立复跑/复核。
覆盖常量链、默认行为、普通变量/动态const、冗余override和严格布尔开关，
另对真实AST副本注入重复ID检验目标及依赖歧义不能被外部域掩盖。
该注入是负例fixture，不是声称Clang实际生成重复声明。远端CI未核验。

完整1068项测试通过（73.774秒，native启用，无跳过），demo/diff通过。
固定重放inputs_unchanged=true，输出SHA256：
`4b2e730c43c7315d4c2e7434c00f951311b723557ff3704732e5fb47f42cd855`。
外层无可推导常量域，内层fresh推导0x195459e8（WARP_SIZE）为[32,32]，
记录依赖0x19545890（next_power_of_two）；不再从外部域文件读取该值。
两项条件checked，次数界仍[0,2]与[0,4]。这只建立本编译工件的源码常量，
不证明真实GPU物理波宽，也不解除其余外部声明域及完整覆盖义务。
