# 用 fresh 初始化入口域检查内层次数界

2026-09-27，基线 `563da13`，无 GPU 执行。

前一轮真实 nested-entry 重放已条件通过（输出哈希
`1ec6113783beb452f4bf4cbe386af712df2cd98dc8bb55a50a62282e52a683bc`）。
本轮不把该报告当作输入证明，而是重新执行入口链及内层边界检查。

```bash
PYTHONPATH=src:. python3 -m experiments.softmax_history_native \
  --native artifacts/wb-native-template-OqD1PQ/native.json \
  --leaf-protocol experiments/softmax-accessible-leaf-protocol-20260927.json \
  --nested-entry \
  --iteration-domain-protocol experiments/softmax-inner-domain-protocol-20260927.json \
  --output artifacts/wb-softmax-derived-bounds-EobLZf/replay.json
```

native SHA256 为
`a59c12247f796fe2034ba03ecc43782f77ac3942496b18a140ceacbb24c7ff45`。
新增外部协议将既有示例区间 element_count `[0,128]` 重新绑定到选定实例的
第 4 号形参（从 0 计数），核对 int 类型和名字；不是从源码猜测合法输入。
local_idx 区间不再作为 caller 给出的入口假设，而由 fresh 入口链获得；
getter leaf `[0,31]` 等更上游前提仍是显式外部条件。WARP_SIZE 等常量由
现有 source-constant checker 重新检查，不是实际物理波宽验证。

GPT-5.6 Sol 新增 5 项真实 Clang 回归并只读复核。正例检查源域 `[0,3]`、
外部 n 域 `[4,8]` 得到每次内层执行的 work_count_bounds=`[1,4]`；缺失/额外
域、覆盖源声明域、历史写入、错 inner、ABI 和伪旧成功协议保持 unknown。
int8 负例明确到达 `signed_arithmetic_may_overflow`，不是在无关语法处失败。
初始 fixture 的不受支持退出分区失败日志保留于
`artifacts/wb-initializer-iteration-bounds-test/initial-unsupported-partition.log`；
改成真实 softmax 使用的受支持分区后，5 项通过（0.684 秒）。未放宽核心分区。

每次实际到达的单次 inner invocation 与 outer 总工作量必须区分。其余外部
区间要求在该次 inner 入口成立；本轮不验证 launch、outer 次数或可达性。
完整验收与重放完成状态见 `docs/status.md`，未完成的运行不计通过。
