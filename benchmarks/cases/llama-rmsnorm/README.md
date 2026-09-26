# llama.cpp RMSNorm logical32 首例

本案例固定 llama.cpp 提交 `b23efaa2ef147f547ee75cbf0c621d61904de80e` 的
`rms_norm_f32<256, false, false>`。`upstream/full/` 保存完整、原样的 `norm.cu`、
`common.cuh` 与 `vendors/hip.h`；`provenance.json` 记录哈希，`standalone.patch` 是从
完整 `norm.cu` 到 standalone baseline 的实际 unified diff。`LICENSE.upstream` 是
该提交的原样 MIT 许可证。

`protocol.json` 在设备运行前冻结有限域和数值比较规则。`reference.py` 是独立 CPU
reference，采用 `float32` 输入、double/`math.fsum` 求平方和，再将输出舍入为
`float32`。它没有调用 baseline，也不读取 `oracle/`。

`baseline/rmsnorm_logical32.hip.cpp` 是可独立编译的正确兼容候选，不是 qdot 翻译：
它追溯到上游 kernel、`warp_reduce_sum<float,32>`、`block_reduce<SUM>` 和 HIP shuffle
shim，保留 XOR shuffle、shared partial、barrier、第二次归约和广播。移除的 PDL、
ggml launch wrapper 及融合/stride 分支在 `provenance.json` 明列。compatibility shim
仅把上游 `__shfl_xor_sync(..., width=32)` 映射到 HIP `__shfl_xor(..., width=32)`。
当前 standalone SDK view 未 force-include Clang HIP math wrapper，因此 AMD 路径显式包含
HIP math declarations，并把 `rsqrtf` 映射到该 wrapper 本身使用的 `__ocml_rsqrt_f32`；
这不替换为 `1/sqrt`，也不改变冻结运算。

人工关系只在 `oracle/manual.json`，不是自动分析输入。
受限自动源码恢复记录见 [source-evidence.json](source-evidence.json)：0dfbbaf 在
完整 standalone HIP TU 上恢复两个列循环、局部贡献、归约链、行前缀和输出后缀，
同时观察到依赖清单与独立 driver 计划任务。这不代表自动处理原始上游 TU、
整核等价或部署门控通过；本次源码分析没有运行 GPU。

父执行者可在 WB-01 已验证的工具链上运行最小 sanity：

```bash
HIP_VISIBLE_DEVICES=0 python3 benchmarks/cases/llama-rmsnorm/runner.py \
  --hipcc /path/to/hipcc --probe-report artifacts/wb01-verified/report.json \
  --nrows 3 --ncols 777 --timeout 60
```

runner 每次创建 `artifacts/wb02-<id>/`，保存实际源码、runner、输入、二进制/输出（若
阶段成功）、命令、stdout/stderr、哈希和比较结果。`passed` 只表示该次输入满足冻结
数值协议；不表示源码自动恢复、一般等价、性能收益、G1 或 WB-03 已通过。
runner 要求 WB-01 报告为 `verified`，并核对可见设备环境及运行时 PCI、arch、HIP
runtime/driver 身份；host 属性中的 warp size 不会单独被当作物理波宽证明。

runner只用于冻结logical32基线，不接受自动生成的候选：任何编译命令前先核对
复制源码与provenance的baseline SHA，以及复制协议与已加载reference协议的
类型敏感一致性，固定launch为width32/block256/shared128。输入不符返回
`invalid_baseline_inputs`。成功执行后，stdout必须只有一个规范的
`logical_width=32`；缺失、重复或错配返回`runtime_protocol_mismatch`，不做数值比较。
该打印字段只是协议一致性检查，不证明物理wave或真实机器码采用对应宽度。
width64候选需要自己的执行协议与全部验收门槛，不能借用本runner的passed。

`evidence.json` 索引九份有效 sanity 报告：在已验证 wave32 的 W7900 上，固定
`nrows=3`，`ncols∈{1,31,32,33,255,256,257,777,1023}` 的全部输出均满足预冻结
容差，观测到的最大绝对误差不超过 `1.1920928955078125e-07`。这些只建立九个
确定 shape 的 baseline sanity，不建立整个协议域、留出谱系、自动恢复或 G1。

另提供供共同案例接入准备的 [CUDA 人工移植](cuda-port.md)，来源、文件哈希和
全部 API 修改类别见 `cuda-port.json`。CPU 回归核对计算函数体除显式 shuffle
API 替换外保持一致；这不是跨 API 语义证明。CUDA host/device 语法检查已通过，
但代码生成、链接和 GPU 数值验证尚未建立，
原 HIP 执行记录不适用于该 CUDA 文件，也不表示 Polygeist 已能接入此案例。
