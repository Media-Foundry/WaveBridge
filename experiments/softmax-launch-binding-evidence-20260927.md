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
