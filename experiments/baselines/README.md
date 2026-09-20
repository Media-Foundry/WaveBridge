# Polygeist 共同案例：先建立前端

`build_polygeist_frontend.sh` 只构建固定 CGO24 版本的 cgeist 前端，**不是完整
CUDA/ROCm 重定向构建**。先用它检查真实 CUDA 输入能否转为 MLIR，之后再分别
建立变换、后端、链接、设备执行证据。前端失败不能替代完整方法的能力比较。

准备独立源码目录并取得精确 LLVM 子模块后，从 WaveBridge 根目录运行：

```bash
bash experiments/baselines/build_polygeist_frontend.sh \
  artifacts/toolchains/polygeist-cgo24 \
  artifacts/toolchains/polygeist-cgo24-frontend-build 8
```

脚本核对 Polygeist `ba9953a08c9bc0965090911b67b2b1e1778cbb59` 和 LLVM
`0b9310c6e4416ee48c07edfef81144e22850dfe7`，要求源码工作树干净。
拒绝已有构建目录，避免混用旧缓存和覆盖证据。失败后保留目录与日志；修复配置
应使用新的目录。构建中断后的恢复需要检查原配置，再显式重跑同目录 build 命令，
不重新调用初始化脚本。默认并行度 8，上限 16；链接任务限制为 1。
链接池通过 `CMAKE_JOB_POOLS` / `CMAKE_JOB_POOL_LINK` 配置，不使用
`LLVM_PARALLEL_LINK_JOBS`：此固定版本在 unified build 中重复载入
`HandleLLVMOptions.cmake`，后者会追加重复的 `link_job_pool`，导致 Ninja 拒绝。
首次实际失败日志保留在本地 `polygeist-cgo24-frontend-build/build.log`。

配置为 Release + assertions、LLVM host target、clang/MLIR，关闭 CUDA/ROCm
runner 和 Polygeist GPU 后端。使用当前 PATH 中的 clang/clang++、lld、CMake、
Ninja，记录版本、编译器/脚本哈希和完整命令。CMake 4 通过显式
`CMAKE_POLICY_VERSION_MINIMUM=3.5` 处理旧版项目的兼容策略；不修改上游源码。

## 为什么前端与 GPU 后端分开

以下是固定提交的源码依据，不是运行结果：

- `tools/cgeist/CMakeLists.txt:20` 无条件构建 cgeist；34 行起才条件接入 CUDA wrapper。
- `tools/cgeist/Lib/clang-mlir.cc:5929` 转发 CUDA include/target 参数。
- `tools/cgeist/driver.cc:600` 在关闭 CUDA 后端时拒绝 `--emit-cuda`。
- `tools/cgeist/driver.cc:1205` 在 `-S` 且不输出 LLVM 时直接打印 MLIR。

构建后先用 `-S` 采集 MLIR，不能使用 `--emit-cuda` 然后把预期的禁用错误记为
工具语义不支持。输入应继续使用案例包的真实 CUDA 头文件与完整 API 移植记录，
不得换成测试 stub 后宣称真实 kernel 支持。

脚本成功只证明 cgeist 可构建。CPU 回归只验证参数和工件保护，不调用编译器构建
或访问网络，更不证明同例转换成功。原始日志保存在构建目录，不自动公开或提交。

## 前端尝试记录

`polygeist_frontend.py` 只执行 `-S -O0` 的 MLIR 输出请求，默认 `--function=*`
保留全输入选择；可显式选择某个 kernel 做诊断，但不能把局部成功当完整 launch
适配。每次新建独占目录，记录源/工具/runner/调用器哈希、命令、原始诊断及部分
输出。状态区分 `tool_missing`、`launch_failed`、`timeout`、`tool_failed`、
`no_ir_emitted` 和 `emitted_unverified_ir`。最后一种不意味着 MLIR 合法或语义正确。
头文件传递闭包未完整哈希，报告明确该限制；没有数值或 GPU 保证。

`-O0` 不等于完全不做变换：固定版 driver.cc 在 626 行起无条件安排 CSE、
canonicalization、Mem2Reg 等 pass，`-O0` 在 664 行附近关闭一部分 inlining。
报告因此标为默认 O0 pass 路径，而不是 identity translation；是否保留通信
和 launch 必须检查输出，不能从命令选项直接推断。

cgeist 与 `clang-resource-headers` 已实际构建成功；不要同时在同一构建目录
启动另一个 Ninja。以下为首次实际运行命令（失败记录见下文）：

```bash
cmake --build artifacts/toolchains/polygeist-cgo24-frontend-build-02 --target clang-resource-headers --parallel 8
PYTHONPATH=src python3 experiments/baselines/polygeist_frontend.py \
  benchmarks/cases/llama-rmsnorm/baseline/rmsnorm_logical32.cu \
  --cgeist artifacts/toolchains/polygeist-cgo24-frontend-build-02/bin/cgeist \
  --resource-dir artifacts/toolchains/polygeist-cgo24-frontend-build-02/lib/clang/16.0.0 \
  --cuda-path artifacts/toolchains/cuda-view-Zt5WBj \
  --include-dir artifacts/toolchains/cuda-12.1-wheels/nvidia/cuda_nvcc/include \
  --include-dir artifacts/toolchains/curand-10.3.2.56-wheel/nvidia/curand/include \
  --include-dir artifacts/toolchains/libcudacxx-1.9.0/include
```

不预判这个完整输入能成功；失败后分别定位工具环境、输入语言范围与实际语义
变换限制。CPU mock 测试只核对记录状态，不计作 cgeist 实验。

2026-09-20 实际执行两次，均为 `tool_failed`，未产生 IR。上面的旧视图缺
`lib`/`lib64`，固定 Clang 的 CUDA 安装检测因此失败。第二次使用独立视图
`artifacts/toolchains/cuda-polygeist-view-LRVuEu`，在原有 include/bin/nvvm
之外，将 lib64 指向同一 CUDA runtime wheel 的 lib 目录；不修改原视图或 SDK。
安装检测通过后，遇到 CUDA 12.1 texture 与 GCC 13 `__noinline__` 头文件错误。
不能忽略这些前置错误，将后续断言归因于 kernel 通信模式。
两份报告和哈希见 [实际执行交接](../../.agents/handoffs/polygeist-first-execution-20260920.md)。

后续 CUDA 11.8 / GCC 11 开发头环境已实际消除上述头错误，但完整输入在
host C++ 对象处理时断言。仅选 kernel 的两次退出 0 都是空 module；记录器
`emitted_unverified_ir` 只代表非空输出文件，必须继续人工或独立 IR 检查，
不能直接统计为支持案例。固定前端以 mangled name 选择函数，并把 device
函数标记为 private；局部选择不能替代保留 host launch 的转换检查。
版本、路径和报告见 [兼容环境交接](../../.agents/handoffs/polygeist-compatible-headers-20260920.md)。

记录器现支持显式 `--cuda-lower`，分别记录默认 O0 与 CUDA lowering 路径；
这不是 `--emit-cuda`，不启用 PTX/cubin 或设备执行，不自动升级验证状态。
实际 host adapter 必须使用默认 `--function=*`：只选 host 入口的本次输出
留下无函数体 kernel 声明，不能用它评价计算。全函数选择已得到非空计算体，
但共享容量和外部 shuffle 仍需检查，见
[实际 IR 交接](../../.agents/handoffs/polygeist-adapter-ir-20260920.md)。

`--emit-llvm` 请求文本 LLVM IR，输出名改为 `output.ll`，报告显式记录
`requested_output_kind`；它不启用 CUDA/ROCm 后端。静态shared诊断副本的
实际 `--cuda-lower --emit-llvm` 尝试失败在未消除的 conversion cast，未得到
LLVM IR。不要把该默认host路径或CPUify路径冒充GPU后端对照，详见
[LLVM路径交接](../../.agents/handoffs/polygeist-llvm-attempt-20260920.md)。

`patches/rocm-wrapper-header-compat.patch` 是对固定上游wrapper的显式环境兼容
补丁，仅在隔离副本编译诊断过，未自动用于构建脚本。它补cstring并临时重命名
CUDA与HIP冲突的surface/texture类型，不删CUDA→HIP函数；不保证设备属性
字段ABI或语义。不能将带补丁构建称为未修改的论文工件，必须保留补丁与版本。
具体成功和失败见 [wrapper交接](../../.agents/handoffs/polygeist-rocm-wrapper-20260920.md)。

`patches/rocm-wrapper-property-audit.patch` 在上述兼容副本上加入42个已复制
字段的sizeof/type断言，当前固定头文件下编译通过；不是完整属性ABI或语义
验证。当前SDK的设备bitcode由LLVM23生成，已实际确认固定LLVM16无法读取
ocml.bc，不能未经门控接入完整ROCm构建。见
[后端前提记录](../../.agents/handoffs/polygeist-backend-prerequisites-20260920.md)。

已从固定ROCm Device Libs 5.3.3提交构建LLVM16可读的opencl/ocml/ockl，
`patches/device-libs-cxx17.patch`只调整host辅助工具语言标准；不改设备算法。
实际构建、typed-pointer验证与联合链接已通过，见
[设备库记录](../../.agents/handoffs/polygeist-device-libs-20260920.md)。
这些库仍需完整后端/目标机器码/实际数值验收，不能凭IR verifier通过宣称GPU正确。

已用独立patched source及独立build启动完整ROCm后端构建，不修改前端缓存。
该构建使用自定义hip::host映射，不是vendor HIP package或论文原环境，
实际配置和恢复路径见 [构建交接](../../.agents/handoffs/polygeist-rocm-build-start-20260920.md)。
构建完成前不能使用预期生成路径宣称工具可用，也不能在同一目录启动另一Ninja。

记录器现在接受成对的 `--rocm-path` / `--amd-gpu-arch`，要求设备库和LLD实际
存在并记录哈希。固定版驱动中，`--emit-rocm -S`只请求GPU MLIR；同时指定
`--emit-llvm`才进入ROCDL lowering及HSACO序列化路径。两者均不是正确性证明，
HSACO请求也不代表序列化已经成功。

该入口禁止同时启用`--cuda-lower`，清除两个alternatives相关环境变量，并在
独占工件目录设置HIP/ROCR/CUDA不可见设备掩码。原因是固定上游的GPU alternatives
静态选择可能调用HIP设备API；不能笼统地声称编译绝不访问设备。掩码不是安全
沙箱，报告仅说明未请求设备执行、未独立观测。实际使用前仍需审查输入与输出
不存在alternatives；不打开`--output-intermediate-gpu`以免污染文本IR。
目前新增路径仅通过CPU编排测试，完整后端仍在构建，尚无这两阶段的新实测结果。

后续实测已完成构建及两阶段诊断，见docs/status.md最新记录。
`patches/rocm-private-alloca.patch`是额外、明确标记的编译器兼容补丁：仅ROCm
设备模块的C-style generic alloca改用AS5分配再转换回原指针类型；不改变host、
CUDA或非generic路径的分支。它不是原论文工件，也不是WaveBridge关系分析算法。
增量构建及受限shuffle诊断已生成无非空未定义动态符号的HSACO，但未执行GPU。
原二进制已保存，详见[补丁验收](../../.agents/handoffs/polygeist-alloca-patch-20260920.md)。

`polygeist_harness.cpp`只负责文件I/O、HIP分配/复制、设备身份和同步，调用生成的
`wavebridge_launch_rms_norm_f32_logical32` C入口，不另写kernel或launch。
使用既有INPUT OUTPUT NROWS NCOLS格式；数值比较须由冻结reference/protocol独立执行。
目前仅通过host编译/链接，尚未执行。它本身不是部署门控：链接工件含GPU注册
constructor，运行前必须由外部核对设备、工件、wave库配置与数值协议。
当前工件wave32 metadata与wave64库控制常量不一致，暂不部署；不能用链接成功放行。

后续 `patches/rocm-device-wave.patch` 在 serializer 优化之前读取实际函数 subtarget，
统一选择 `__oclc_wavefrontsize64`；波宽未知或模块内混合时拒绝。该补丁叠加在
上述带补丁的固定 Polygeist 构建，不是上游原版或 WaveBridge 分析算法。
双目标静态复测已得到 gfx1100 wave32/常量0、gfx90a wave64/常量1；原 host harness
仍绑定旧工件，不能直接运行。尚无GPU数值验收；详见
[波宽补丁记录](../../.agents/handoffs/polygeist-wave-patch-20260920.md)。

设备执行后发现O0数值失败，分阶段诊断中局部累加已经错误。相同人工输入改为
O1后通过本机W7900的9个确定性形状；记录见
[O1数值验收](../../.agents/handoffs/polygeist-o1-numeric-20260920.md)。
正式 `polygeist_frontend.py` 现支持 `--optimization-level {0,1,2,3}`，API对应
`optimization_level=1`。默认仍为0，保持旧调用行为；复现上述人工基线须显式选择1。
报告记录整数 `optimization_level`，pipeline标签与命令中的-O级别一致，编译成功
仍仅为 `emitted_unverified_ir`，不自动继承先前的GPU数值结论。O2/O3仅有编排测试，
没有设备结果。不要使用旧入口报告或旧harness冒充O1结果。
