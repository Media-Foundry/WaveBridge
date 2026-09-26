# 真实 softmax 相对输出写入检查

2026-09-27，基线 `68a6fbe`。只分析已冻结源码 AST，不执行 GPU。

新增检查 fresh 重建已有入口与次数证据，不接受旧成功报告；再检查实际
work 的每条路径恰好一次 store、精确输出形参，以及相对当前指针的下标
`outer*element_count + it*WARP_SIZE`。列 guard 另须对应
`local_idx + it*WARP_SIZE < element_count`，且 header 容量不能截断外部域。

```bash
PYTHONPATH=src:. python3 -m experiments.softmax_history_native \
  --native artifacts/wb-native-template-OqD1PQ/native.json \
  --leaf-protocol experiments/softmax-accessible-leaf-protocol-20260927.json \
  --nested-entry --guarded-stores \
  --iteration-domain-protocol experiments/softmax-inner-domain-protocol-20260927.json \
  --output artifacts/wb-softmax-guarded-stores-G3FGoC/replay.json
```

本轮重放已启动，日志在同目录 `run.log`；完成状态须以实际报告为准，
目前尚未取得终态，不记为通过。
native SHA256 为 `a59c12247f796fe2034ba03ecc43782f77ac3942496b18a140ceacbb24c7ff45`。
相同外部 getter 域 `[0,31]` 和 element_count 域 `[0,128]` 均未升级为设备事实。

GPT-5.6 Sol 补充真实 Clang 回归并只读审查，5 个测试方法通过（4.681 秒）。
正例含直接及互斥分支写入；负例具体断言错误 index/base、双写、漏写路径、
N=129 截断、额外 source-source 读取、中间整数溢出与分支/RHS 副作用。
RHS 写入 N 由 fresh 上游保持检查拒绝，报告没有将其冒充新层的效果检查。
初始样例的全局 step 不在旧前缀子集内，改为局部 const 后才执行上述验收；
同时修复新接口默认不开静态分支时缺少列表字段的 KeyError。

完整验收：1137 项测试通过，81.431 秒，native 插件启用、无跳过；
`make demo` 与 `git diff --check` 通过。日志在
`artifacts/wb-guarded-stores-check-pbTe45/`。
核心源码 SHA256：`95f0bdda32ce97f0975a86fb02f5fc772745ba4db3ddf0312d5cf140c4da0692`。
回归源码 SHA256：`a9df3fec62353518eeab191b2ce96e42e55d159d59ef7610993ed37b9e567333`。

## 保证边界

即使局部检查通过，先前 `dst += idx_offset` 的语义与行/lane 身份仍未建立；
不能宣称这些 store 已完整覆盖输出数组。源 AST、声明、路径和局部下标的
绑定与全 kernel 的内存有效性、浮点值和协作通信是不同义务。
报告明确保留 pointer-history、lane-family、full-output-coverage、source 与
deployable 标记为 false。CPU 合成负对照也不替代这份生产源码分析。
