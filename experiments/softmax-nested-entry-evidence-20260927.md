# 初始化域到实际内层入口的组合

2026-09-27，基线 `0faa378`，无 GPU 执行。

外层首次入口历史已按 `0faa378` 的实现完成真实重放，详见
[历史实录](softmax-native-history-evidence-20260927.md)。这还不够支持内层
入口域：内层前的外层写入影响本次入口，内层后的写入影响下一次外层迭代。
原 work checker 的内层依赖集合不自动覆盖这些兄弟语句。

新增组合入口 fresh 检查历史，并从外层扫描开始保护同一个源声明。原始
外层 header、prefix、guard、全部 work 都检查；内层继承额外保护，最后
要求选定内层 ID 对应唯一的 checked 嵌套路径。它不是直接拼接旧成功报告。

真实重放命令：

```bash
PYTHONPATH=src:. python3 -m experiments.softmax_history_native \
  --native artifacts/wb-native-template-OqD1PQ/native.json \
  --leaf-protocol experiments/softmax-accessible-leaf-protocol-20260927.json \
  --nested-entry \
  --output artifacts/wb-softmax-nested-entry-ujZgP9/replay.json
```

输入 native SHA256：
`a59c12247f796fe2034ba03ecc43782f77ac3942496b18a140ceacbb24c7ff45`。
实际绑定历史调用四项（infinity、Max、exp、Add），工作调用为
`0x30de6178`（quiet_NaN）；采用同一次 AST 的静态分支选择。
所有 getter/leaf 值域与效果仍是显式外部前提，不因加入组合就得到验证。

GPT-5.6 Sol 新增 5 项真实 Clang 回归并只读复核：正确嵌套、内层前后写入、
引用别名、外层 header/history 写、错误/非嵌套 ID、伪成功协议与 ABI 边界。
专项初跑 5 项通过（0.779 秒），独立重跑通过（0.778 秒）。
完整验收和实际重放状态见 `docs/status.md`；未完成的运行不记为通过。

保证仅限每次实际到达指定内层入口时的条件域保持，不证明可达性、次数、
终止、循环整数安全、完整迭代域、数值等价或 GPU 部署。即使入口保持通过，
还需连接同一 AST 的循环边界检查；local_batches 等外部输入域也没有因此解除。

## 563da13 实际重放结果

已完成：status=checked，inputs_unchanged=true，输出 SHA256
`1ec6113783beb452f4bf4cbe386af712df2cd98dc8bb55a50a62282e52a683bc`。
结果域 `[0,31]`，outer `0x30de67f8`，inner `0x30de6780`，相对路径
`[4,2,1]`；历史和工作两组 unused 协议均为空。结束后逐文件核对实现哈希
与当时工作树一致，再开始次数边界组合实现。该检查不建立工作次数界。
