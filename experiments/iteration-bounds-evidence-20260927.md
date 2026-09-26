# 退出循环的条件整数安全与工作次数界

2026-09-27，wb03-source-ast，基线9d48912。无GPU、无生产AST重采。

```bash
PYTHONPATH=src python3 -m experiments.softmax_exit_guards \
  --native artifacts/wb-column-builtins-twz82w/native.json \
  --recovery artifacts/wb-loop-calls-SIr4BJ/all-calls.json \
  --work-preservation --static-branches --nested-loops \
  --iteration-domains experiments/softmax-exit-domains-20260927.json \
  --int-bits 32 --output artifacts/wb-iteration-bounds-L6QCW8/replay.json
```

固定native SHA256：
`317b1a438bc13845cf76b5aa7461db4db2081b402c457a85c4160fdd7257c027`；
固定旧recovery SHA256：
`31a6570762225ea247f24b799be28ebd51f3dab13e562e32cccb8e305d764f67`。
示例域文件SHA256：
`5a3380c196f0d0356047426abfad3fbf6bdb445d6845300852a2afff1e1c4c5e`。
这些ID只对该固定AST有效，不按名称套用到其它编译工件。

声明域全部是本次显式外部假设，不是新恢复结果，也未证明来自实际launch：

| 精确声明 | 角色 | 外部区间 |
| --- | --- | --- |
| 0x19546658 | local_batches | [0,2] |
| 0x194e0b80 | element_count | [0,128] |
| 0x195459e8 | WARP_SIZE | [32,32] |
| 0x19546950 | local_idx | [0,31] |

其中WARP_SIZE区间也按外部前提处理，本入口不据此宣称完成常量/初始化域绑定。
header start/bound/step则来自原始AST的fresh观察和常量检查。
checker重新执行work保持性，并按原始有序prefix DAG逐次计算整数区间。
每个prefix包括退出当次都检查；仅当work仍可能执行才检查后继increment。
确定退出后不虚构后续prefix。未知比较会保守扩大次数界，而非按false处理。

范围只针对所选loop的header、prefix、guard和work次数上下界。不检查work
内的全部数组下标/浮点表达式，也不递归签发nested算术安全；不能用内外层
分别checked代替统一输入/到达条件证明。旧6/8恢复、完整迭代域和部署状态不提升。

实际验证命令：

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_loop_exit_iteration_bounds_clang.py' -v
WB_NATIVE_CAPTURE_PLUGIN=/home/husrcf/Code/ProtBind/wavebridge/artifacts/wb-native-builtins-JR99CL/libwavebridge_capture_plugin.so \
WB_NATIVE_CAPTURE_COMPILER=/opt/AMD/aocc-compiler-5.1.0/bin/clang++ \
make check
make demo
git diff --check
```

新增5项真实Clang回归通过（0.362秒），GPT-5.6 Sol负责测试与只读复核。
覆盖确定/不确定break、trailing prefix DAG、退出当次prefix和后续prefix溢出、
possible work的末次增量与definite break对照、域缺失/多余/strict整数、预算与
work修改依赖。日志保存在artifacts/wb-iteration-bounds-L6QCW8/，远端CI未核验。

完整1063项测试通过（73.616秒，native启用，无跳过），demo/diff通过。
固定回放inputs_unchanged=true，输出SHA256：
`68872954df5434bdfd17bd211e09098aa3d3ac32e76368a2f1be7d8048f6c890`。
外层work次数界[0,2]、内层[0,4]，两项条件checked；此宽输入盒下所有退出
比较均为unknown truth，不因此裁剪任何潜在work。内层四个prefix值区间
依次[0,31]、[32,63]、[64,95]、[96,127]，受检中间运算及可能增量在声明
int32范围内。iteration_bounds_established=true，但完整域/源程序/部署
仍false，不把区间界当成全部列覆盖证明。
