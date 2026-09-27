# 真实 softmax kernel/launch 精确绑定

2026-09-27，基线 `6f667af`。复用已有 `launch_binding.check`，不增加手写
lane 列表，不修改正在运行的 pointer-history 检查源码或其 driver。

```bash
PYTHONPATH=src:. python3 -m experiments.softmax_launch_native \
  --native artifacts/wb-native-template-OqD1PQ/native.json \
  --output artifacts/wb-softmax-launch-native-VU50pj/report.json
```

结果 checked、inputs_unchanged=true，结束后逐文件实现哈希与当前源码一致。
报告 SHA256：`64f13be67f51ff19673b1fbc8b72e23840e8718238a4ca52ed546aeec0f6f4db`。
native SHA256：`a59c12247f796fe2034ba03ecc43782f77ac3942496b18a140ceacbb24c7ff45`。

## 实际身份

- 预选 kernel：`0x30d762e0`，仍为固定 float/float/float/L2E=7 实例。
- 唯一匹配 launch：`0x30d76610`；配置函数：`0x2e3828b0`。
- 四槽表达式：`0x30d75610`、`0x30d75650`、`0x30d75688`、`0x30d75768`。
- slot0 从 blocks `0x30d69980` 构造；slot1 为 threads `0x30d69b78` 的复制。
- slot2 是转换后的字面量；slot3 包含 getCurrentCUDAStream 调用。
- 8 个 kernel 实参按位置绑定到 dst、src、batch_count、softmax_elements_stride、
  softmax_elements、mask、chunk_size、is_transformer_mask 的对应形参。

完整 TU 另有 22 个未解析 launch 位置，保留在报告里。当前结论只是上述精确
选点绑定，不是全部 TU 解析成功；也没有根据其他位置的失败否定已选绑定。

## 尚未建立

`configuration_values`、`source_object_preservation`、`host_reachability` 与
`launch_API_semantics` 均为 not_established。没有证明 block.x=32、完整唯一
lane 家族、成员全部到达 store、实际物理波宽、GPU 或整核/部署保证。

真实 host 使用只有声明的 `at::cuda::warp_size()`，再计算 warp_size 与二维
threads。后续必须绑定其 API 条件、对象字段/历史和实际 x getter，不能从
getter 的区间 `[0,31]` 直接构造已证明的线程多重集。完整参与还需单独检查。

定向真实 Clang 回归：8 项通过，0.137 秒，日志同目录 `tests.log`。
本次仅新增重放 driver，未改 checker；`make demo`、`git diff --check` 通过。
提交 `6f667af7312a792ff8bb1584c0665b8d5f2afb7b` 的
[CI 36280680885](https://github.com/Media-Foundry/WaveBridge/actions/runs/36280680885)
已只读核验 completed/success，不作为 GPU 证据。

## threads 对象的首次实测诊断

GPT-5.6 Sol 在同一 native 输入上仅执行一次现成入口：
`object_use_closure.inspect_structure(payload, "0x30d69b78", ABI, {}, max_ast_nodes=10_000_000)`。
报告为 `artifacts/wb-softmax-threads-object-diagnostic/report.json`，SHA256
`b1e5d6fbc9ed9e1a4009b8685a020e7aaf9f0a07a5e4a91b26332eeb557902a1`。
父检查 unknown，原因 `fresh_conditional_object_initialization_not_checked`；
fresh 初始化在 constructor `0x30d69d08` 处返回
`target_not_direct_local_of_ordinary_nontemplate_function`。fields 为空，
post_initialization_value_preservation 未建立。此诊断未修改源码，也未运行 GPU。

因此，首个未解除义务是模板实例作用域支持，不是已经证明的复制后字段变异。
不能直接把构造实参 `warp_size, warps_per_block, 1` 当作 launch 复制时的值。
后续即使扩展实例支持，也必须保留精确声明绑定、初始化效果和历史保持检查。

后续只读代码复核（不是运行结果）定位到三处一致性门槛：
`object_initialization`、`constructor_argument_effects`、`object_use_closure`。
不能只删除一处 template guard；应先绑定唯一、完整、非 dependent 的函数
实例和函数体，再以实例内 child path 区分共享语句 ID。模板本体、歧义身份、
跨实例路径和无法绑定的共享节点继续拒绝。即使该门槛解除，动态读取
`warp_size`、`warps_per_block` 仍不属于当前构造值 literal/min-selection
子集，不能跳过它们到构造点及复制点的历史。这些是下一步实现约束，非已通过项。
