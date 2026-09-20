# LLVM 输出路径诊断

- 日期2026-09-20，分支 `wb03-source-ast`，基线 `6e4731f`；中文回复，
  直接本地commit，不创建PR、不推送。
- runner新增严格布尔 `emit_llvm` / CLI `--emit-llvm`，输出 `.ll` 和类型标签；
  所有结果仍未独立验证，不启用GPU backend。两项新mock回归不计真实能力。
- 主代理用原静态shared诊断副本、相同CUDA11.8/GCC11头和固定cgeist，实际
  全函数选择 `-S -O0 --cuda-lower --emit-llvm`。完整命令（含一次重复但相同的
  GCC架构include路径）及诊断在 `artifacts/polygeist-frontend-y5jbgv2s/report.json`。
- 报告SHA-256：`37520ff0cacc5749a8e006e7364040378a28d3267964725cd9f3abad3f6acaee`。
  状态tool_failed，退出255，ir=null；不是LLVM成功发射。

实际首个错误是 `builtin.unrealized_conversion_cast` 缺少LLVM翻译接口；
stderr打印的部分MLIR还含async执行结构与外部shuffle。不要用部分dump当
LLVM IR，也不能把预期的barrier转换问题替代实际首条诊断。

Sol只读核查固定driver：不启用emit-cuda/rocm时EmitGPU=false，CUDA lowering
使用CPU侧parallel表示；不加cpuify时不会经过CPU barrier处理，而默认emit-llvm
会进入OpenMP/LLVM转换。CPUify是另一执行模型，不是本任务的GPU适配证据。
真正GPU路径的outline及GPU→NVVM/ROCDL受GPU后端配置控制，当前构建未启用。

主代理 `make check` 282项通过；核对报告hash、实际诊断及 `git diff --check`。
未执行LLVM代码、GPU、数值或性能。开始准备同固定版本的Clang工具，以便后续
检查ROCmRuntimeWrappers的实际构建前提；不能用已安装的新Clang替代旧版typed
pointer bitcode需求。整体G1仍未通过。

随后实际完成 `cmake --build artifacts/toolchains/polygeist-cgo24-frontend-build-02
--target clang --parallel 8`，15/15，退出0；版本为Clang16.0.0、同固定LLVM SHA。
`bin/clang-16` SHA-256为
`048c6a9ae4bb1a4d4fadbd1ce98ab3648c2e1f8fb7c74380c09a65cbe089d41f`。
原cgeist哈希仍为 `fcbc0e8eb3466b4cde2521f2691c3fae534e13112d2b73b59a779b2e0a564903`，
未重新配置构建或修改上游。ROCm wrapper和完整GPU后端尚未构建。
