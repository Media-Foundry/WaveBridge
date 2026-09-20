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
