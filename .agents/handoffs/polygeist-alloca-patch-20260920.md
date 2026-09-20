# 交接：ROCm alloca 兼容补丁验收

- 日期/分支/基线：2026-09-20，wb03-source-ast，c4874b3；中文、直接commit，无PR/push。
- Sol子代理仅修改固定worktree的ConvertPolygeistToLLVM.cpp；主代理审查并保存
  experiments/baselines/patches/rocm-private-alloca.patch，SHA256
  `d4fd2bea0ad3054dd9e850b1d86692334e6197bccf12da1ed361b8408beed986`。
- 显式开关gpuModule && gpuTarget==rocm；仅converted pointer AS0用AS5 alloca
  再addrspacecast回原类型。host/CUDA/nonzero-AS走原分支；不修复生命周期或逃逸。
- 原cgeist及原源码保存在artifacts/toolchains/polygeist-before-alloca-1aJe8t/，
  cgeist hash ef5fb79acf82db9ebcdcdadf5d0a35d0eb89615bbc0896eccb5f8266918ad054，
  源码hash 23c6759d7a917f5c882d2f585ea9cce3f8ecfd8f86072cfae3d9c5786f6b71bd。
- 原build-02增量`cmake --build ... --target cgeist --parallel 8`三任务退出0；
  日志artifacts/polygeist-alloca-regression-xpWINL/build.log（含原有警告）。
  新cgeist hash `97b159d7c7fc7f19be813282e91f567a7acff518d99ee5b5bfc174dee97f491e`。
  不再把此路径当作未加alloca补丁的旧二进制。
- host回归：同目录host.c包含地址逃逸的局部int，两版cgeist -S -O0 --function=*
  --emit-llvm生成host-before/after.ll，cmp无差异，hash
  `e42e96c3c07900cc13e76b2990f2a603211b134ccf26aff200eea6e641ae8939`。
  host测试不是CUDA分支运行验证；CUDA分支仅作代码边界审查。
- 同一shuffle诊断源码不变（hash87aab91b），沿用既有环境/参数实际重跑。
  artifacts/polygeist-frontend-awqe6wf1/report.json退出0，hash
  `a67b63b78dd4033784f37a7db150b6419ff3ffaec2fc1e704a43f769594dedbf`；
  output.ll hash `3ea5d8d92121e93db6883176d8048ea11f8e4ffe5f2908fff3582251d8d5e3ca`。
- 提取embedded.hsaco 8984字节，hash
  `33ec479b36b2b59c993aff9cee9796264b73c8b7eaf37163a90cddcf9c2f41f4`。
  同目录readobj.log绑定kernel95645752734432：gfx1100、wave32、shared128、
  kernarg24字节，动态符号表除空占位外没有未定义项。
- `make check`284项通过；这些CPU测试不验证外部编译器补丁的GPU语义。
- 未执行GPU加载/数值/性能。无未解析符号不是完整正确性；仍需检查convergent
  传播、wave库常量与实际lane行为、独立reference及冻结数值协议。
- 下一步：对生成工件执行部署前静态核验，设计最小受控数值验收；明确这是人工
  baseline适配成本，不能替代WaveBridge自动恢复、检查及跨宽度改写的贡献。
