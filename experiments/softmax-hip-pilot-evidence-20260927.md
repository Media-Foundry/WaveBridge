# PyTorch softmax 手工 HIP 基线：首次执行闭环

2026-09-27，基线 `14510bf`。使用用户授权的本机W7900；按run-experiment流程
先做设备预检，选择逻辑设备0、设置HIP_VISIBLE_DEVICES=0。无远端、训练或调优。

## 输入与兼容边界

输入仍来自PyTorch `a8d6afb511a69687bbb2b7e88a3cf67917e1697e` 的
PersistentSoftmax.cuh，原文SHA256
`12436933cae8c1e4096af342313070ce873eefad3d6a1637675ef780d1fdea1e`。
许可/来源见原冻结intake协议。生成的上游派生文件只存本地artifacts，不随Git分发。

这是一份**新手工HIP工件**，不是之前CUDA sm80输入或自动变换结果。
runner逐个核对替换上下文数量，保存完整patch及改写前后哈希：

- 三个依赖include替换；kernel运算、循环和dispatch主体不重写。
- 两个launch宏增加返回原grid的配置记录包装，只有forward路径实例化执行。
- compat头提供HIP shuffle与assert/launch错误检查；手工device query实际
  调用hipGetDevice/hipGetDeviceProperties，不返回假定的32。
- `getCurrentCUDAStream()`手工映射default HIP stream，不是PyTorch当前流。
- 编译期C10_WARP_SIZE显式专门化为32；host设备属性、device probe和选定
  softmax实例编译metadata须一致。此项是手工目标配置，不是自动恢复。
- 显式引入所选Clang的HIP runtime wrapper，以提供设备math overload实现。

原USE_ROCM的warpSize表达式在本机SDK中不是constexpr，不能直接用于该旧
上游模板。编译期专门化修订发生在任何GPU数值结果之前，不据结果调容限。
不把该兼容实现称为未修改的完整生产TU或完整PyTorch运行库。

## 冻结面板与工程修订

协议为 `benchmarks/intake/pytorch-softmax-hip-protocol.json`，参考为独立
`experiments/softmax_hip_reference.py`。rows={1,3,17}、columns={65,128}、
zero/sawtooth/alternating三种输入，共18案例；float32连续输入，float64
稳定softmax参考。逐元素门槛为2e-6+2e-5*abs(reference)，行和门槛2e-5。

禁用mask但提供有效零mask缓冲。初次pilot后进一步将backing allocation
补齐到8行块的整数倍，让inactive尾组预先形成的指针留在分配对象内；逻辑
rows、输入值和计算不变。旧padding“仍为NaN”检查不能证明未写入，最终改为
按位比较0x7fc12345 sentinel，字段仅称padding_sentinel_preserved。即使位
模式保持，也不证明没有发生同值写入。协议明确记录这项启动后的工程修订。

## 命令与同一工件的证据

```bash
HIP_VISIBLE_DEVICES=0 PYTHONPATH=src:. python3 experiments/softmax_hip_pilot.py \
  --source artifacts/wb03-vllm-holdout-GqLQJo/torch251/torch/include/ATen/native/cuda/PersistentSoftmax.cuh \
  --output artifacts/wb-softmax-hip-pilot-20260927-10 \
  --hipcc artifacts/toolchains/sdk-view-sx4rmd37/bin/hipcc --run
```

输出目录必须不存在；不带--run只编译。工具缺失、编译失败、metadata未建立、
设备预检不满足、运行失败、数值失败不作为通过；失败CLI返回非零。
初版失败记录中的CLI零退出不代表成功，应读取其明确失败status。

最终report SHA256：`f53b5800c54e8ef5ec459b7734e3c4edf0a6064e8e519357881926e28b78cab2`。
binary SHA256：`e701e27e45191a6db5d0ea8aa4412f3300db1f99b00c6da5d29d541276750978`。
完整输入/适配文件/二进制前后哈希一致；提交的结果索引保存逐case统计和raw引用。

设备报告AMD Radeon Pro W7900、gfx1100，PCI domain=0/bus=83/device=0。
HIP driver/runtime均71526333，API实际加载库由进程内dladdr记录为
`_rocm_sdk_core/lib/libamdhip64.so.7`，SHA256
`1a8bcd00d05cce36bebcf4acf30289f36f6562ec532e9c618c42e9bd2d90ed05`。
SDK view中的实际clang、hip_version、runtime与ocml文件均fresh哈希核对一致。

所选L2E=7实例的编译器输出metadata为wavefront_size32；同一可执行文件的
device probe读到32，host API调用一次读到32，softmax dispatch trace一次，
block=(32,4,1)，grid分别1/1/3。probe是额外kernel，dispatch计数不包括它。
这些是有限运行与编译证据，不是最终机器码的形式证明。

18/18数值通过，最大元素绝对误差 `1.6796065205326727e-8`，最大行和误差
`7.594798701049399e-8`。最终padding sentinel保持。padding前后pilot输出
逐项一致。没有测kernel性能，subprocess耗时不得当kernel latency。

## 失败与修订原样保留

所有目录为 `artifacts/wb-softmax-hip-pilot-20260927-XX/`：

| XX | 结果 |
| --- | --- |
| 01 | 系统/opt/rocm缺hip_fp16头，编译失败 |
| 02 | 既有完整SDK中warpSize非constexpr，编译失败 |
| 03–04 | 设备exp(float)定义缺失，调整include顺序仍不能链接 |
| 05 | 显式Clang HIP wrapper后编译通过，普通沙箱设备初始化失败，无kernel执行证据 |
| 06 | 提升已授权设备访问权限，18案例通过 |
| 07 | 加入运行库身份记录，18案例通过 |
| 08–09 | padding工程修订与面板/工件门控复验，18案例通过；旧untouched标签不作保证 |
| 10 | 最终按位sentinel与准确字段，18案例通过 |

05初版report的GPU_executed误记为“已尝试”；根据原始stderr及首个hipSetDevice
失败只能判定未执行kernel。后续runner分别记录attempted、未知和confirmed，
不回写旧报告。各轮共享同一18-case科学面板，不算多个独立benchmark。

完整1205项CPU检查通过（93.310秒，native启用、无跳过）；最后8项定向复验
通过，demo/diff通过。全量日志位于08/check-final.log；首轮协议状态断言
未同步的失败日志保留在06/check.log，更新断言如实区分工程修订与数值冻结。
GPT-5.6 Sol负责独立reference/协议、测试与只读复核，并发现padding保证过度。

## 下一步与仍未成立的结论

现在有同一手工HIP host/kernel/runtime的有限执行证据，但旧CUDA AST的
精确ID与检查结果不能搬过来。下一步针对**这份最终HIP工件**重新采集AST及
依赖，把实际配置和API来源连接到源码关系；随后才研究自动候选与目标检查。
本轮不是完整生产TU、PyTorch runtime linkage、native64适配、性能收益、
形式验证或WB-03/04完整验收。source_program_checked/deployable仍false。
