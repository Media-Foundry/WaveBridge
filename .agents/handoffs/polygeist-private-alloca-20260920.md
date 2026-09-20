# 交接：局部栈地址空间断言定位

- 日期/分支/基线：2026-09-20，wb03-source-ast，b6dee2d；中文、直接commit，无PR/push。
- 目录：artifacts/polygeist-shuffle-ir-debug-nRoZ9N。
- capture.py复用上一轮失败报告的完整命令，增加--output-intermediate-gpu，
  显式env LD_LIBRARY_PATH并使用新cwd/output；report.json保存命令、前报告hash、
  stdout/stderr和返回-6。混合stdout是诊断日志，不是干净的LLVM工件。
  report hash `fd5ece02abb52e500aa0b95a58eaab84d259644557bc55ff423c3c3ab8f0fa0e`。
- extract_ir.py按唯一Optimized GPU LLVM module标记提取device.ll，hash
  `813e332cd1be03e77b47eebd07b7ba9c6e6bf7592b5864223aab924fb0f170e6`。
  固定LLVM16 opt -opaque-pointers=0 -passes=verify -disable-output通过。
- 独立新build/bin/clang执行：
  `-target amdgcn-amd-amdhsa -mcpu=gfx1100 -nogpulib -x ir -O0 -S device.ll -o device.s`，
  同样在diagnostic_xor32函数SelectionDAG::getNode/visitBitCast断言，driver退出1。
  verifier通过不表示目标代码生成前提成立。
- 人工IR诊断副本device-private-alloca.ll，仅改三处alloca：float/i32/float
  分配指定addrspace(5)，紧接addrspacecast回原generic指针，其他语句不变。
  hash `51327ba7808c2e0b6f31e1805ef8592638fc5a38a825947945b8df8bf602a160`。
  相同opt验证及相同clang命令退出0，生成device-private-alloca.s，hash
  `a00095f89dabbd582fed9d8716c5075ae6084adac3143ff54c238c5c3a6261cd`。
- 汇编第319行为.amdhsa_wavefront_size32 1；第993行有OCKL helper定义，
  第1011行为ds_bpermute_b32；不是只把外部shuffle改了名字。
- 固定Polygeist ConvertPolygeistToLLVM.cpp:934-955的CAllocaOpLowering使用
  memref转换后的指针类型直接构造AllocaOp；当前helper最终是generic allocas，
  目标data layout则A5。受控三处改动消除故障，支持定位到此栈地址空间路径。
  不扩大结论为所有AMDGPU stack lowering均已修好。
- 未执行：修改编译器、完整源码到HSACO重跑、GPU加载/数值/性能。
  手工IR修复和API兼容副本不是自动适配，不作为WaveBridge算法贡献。
- 下一步：限定ROCm设备模块的最小栈地址空间兼容补丁及回归，保留原baseline
  二进制/源码/报告；然后检查完整工件、convergent属性及wave库前提，才能考虑数值验收。
