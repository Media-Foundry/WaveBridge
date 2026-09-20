# 交接：ROCm 编译阶段门控

- 日期/分支/基线：2026-09-20，wb03-source-ast，917fe24。
- 用户约定：中文回复；直接本地commit，不创建PR，不自动push/merge。
- 改动：polygeist_frontend.py新增显式ROCm路径、gfx目标、依赖哈希及阶段字段；
  tests/test_polygeist_frontend_attempt.py覆盖参数拒绝、命令编排和保证不提升。
- 实际验证：`make check`退出0，284项测试通过。新增ROCm测试使用mock，
  不证明工具可运行、输出正确或设备不可访问。
- 固定版驱动的阶段区别：`--emit-rocm -S`跳过要求EmitLLVM等条件的后段，
  只输出GPU MLIR；加`--emit-llvm`才请求ROCDL lowering、HSACO序列化及host LLVM。
  二者都必须重新检查完整kernel/launch、外部shuffle、共享容量和alternatives。
- 安全边界：上游LowerGPUAlternativesOp静态选择会调用HIP API。入口禁止
  cuda-lower，清除POLYGEIST_GPU_KERNEL_BLOCK_SIZE和
  POLYGEIST_GPU_ALTERNATIVES_PRINT_INFO，设置三种不可见设备掩码，使用独占cwd。
  这只是防误触措施，不是沙箱或无设备副作用证明；不请求GPU执行。
- 未执行：新的ROCm记录器实际编译、HSACO检查、GPU数值或性能测试。
- 构建仍在运行：session 29377，目录artifacts/toolchains/polygeist-rocm-build-02；
  最近观测1572/3895。只继续原会话或读取build.log，不启动第二个Ninja。
- 下一步：构建结束核对cgeist/clang/lld/wrapper，然后对原host adapter与
  静态shared诊断副本分别运行GPU MLIR及LLVM请求；不加cuda-lower。
- 本提交不含构建产物，不推送；GPU后端可用性、wave模式和完整ABI尚未建立。
