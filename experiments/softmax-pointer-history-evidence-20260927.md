# 入口输出指针的条件历史检查

2026-09-27，基线 `f19281c`，无 GPU。前一项真实相对 store 重放已通过，
但仍明确未建立此前 `dst` 偏移。本轮不输入旧成功报告，而是 fresh 重建。

## 支持与前提

输入为同一 native AST 及独立声明角色绑定。恢复 `idx_offset=first_batch*stride+local_idx`，
检查直接语句顺序与唯一 `dst += idx_offset`，全函数审计 dst/offset 引用，
拒绝存储写入或地址/引用逃逸。Clang 的 `array_filler` 语义槽位不可漏扫。
每个中间 int 运算单独检查，不能用代数消项隐藏溢出。

外部开发窗口提前冻结在 `softmax-pointer-domain-protocol-20260927.json`：
first_batch `[0,4095]`、stride `[0,128]`，含义为 offset initializer 求值时。
它不是自动恢复的 row/launch 域，不是 GPU workload，也不暗示 stride=count。
已有 source `[0,31]` 来自 fresh 初始化保持链，但其 getter leaf 域仍是外部前提。
指针有效数组对象、非局部控制排除、动态别名与 FP 等边界均保留。

## 验收与真实重放

在隔离工作树 `/tmp/wb-pointer-dev-rhMgXx` 实现，未影响上一项进行中的输入
哈希核验。GPT-5.6 Sol 负责 5 项真实 Clang 回归并只读复核；包含二次/条件/
错序更新、地址与引用逃逸、goto、lambda、static row、域、角色及溢出负例。
array_filler 隐藏逃逸案例明确核对旧 store 层通过、新层以对应原因拒绝。
完整 1148 项测试通过（92.048 秒，native 启用），demo/diff 通过；日志在
`artifacts/wb-pointer-history-check-q532dC/`，后缀 `-isolated`。
主树源码与测试逐字节比对一致；移入后的完整复验再次通过 1148 项，
91.888 秒，native 启用且无跳过，demo/diff 通过，另记 `-main` 日志。

```bash
PYTHONPATH=src:. python3 -m experiments.softmax_history_native \
  --native artifacts/wb-native-template-OqD1PQ/native.json \
  --leaf-protocol experiments/softmax-accessible-leaf-protocol-20260927.json \
  --nested-entry --guarded-stores \
  --iteration-domain-protocol experiments/softmax-inner-domain-protocol-20260927.json \
  --pointer-domain-protocol experiments/softmax-pointer-domain-protocol-20260927.json \
  --output artifacts/wb-softmax-pointer-history-0KgDSq/replay.json
```

该真实重放已启动，尚未取得终态，不记为通过。日志在同目录 `run.log`。
即使本层最终通过，也不证明完整输出覆盖、lane-family 或整核/部署安全。
