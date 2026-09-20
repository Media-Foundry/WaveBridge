# 交接：显式 OCML rsqrt 链接探针

- 日期/分支/基线：2026-09-20，wb03-source-ast，5df19f3；中文，直接commit，无PR/push。
- 目标：把已知的数学映射缺口与shuffle缺口分离，不改归约或编译器。
- 输入：artifacts/polygeist-ocml-rsqrt-Aqnf6f/adapter.cu；基于已记录静态shared
  副本，仅增加`extern "C" __device__ float __ocml_rsqrt_f32(float);`声明，
  并将scale的rsqrtf调用改成该符号。人工API适配诊断，非自动math.rsqrt提升。
  SHA256 `0071ef7365afa10f7e3579f969978aa411486e9fdae91548fb074024ff1c5500`。
- 执行：沿用首个ROCm工件的cgeist/CUDA头/GCC头/backend-view，O0、function=*、
  gfx1100、sm_70、--emit-llvm、不加cuda-lower，完整argv在报告。
  LD_LIBRARY_PATH=/home/husrcf/anaconda3/lib/python3.12/site-packages/_rocm_sdk_core/lib，
  PYTHONPATH=src；runner保留三种设备不可见掩码，但不是硬隔离证明。
- 实际退出0，报告artifacts/polygeist-frontend-y895g0ib/report.json，hash
  `a90f86972646b032a82ed9636d420f31b87b94b566d4b1f98d2d0a20677b01f9`；
  output.ll hash `3dd9021d8b3d32f227df8d016ed648e13f2bb7b097a362d2e5f0238d93edebc5`。
- 复用诊断LLVM字符串解码脚本提取embedded.hsaco，9016字节，hash
  `9a7edff197c8fd48ab42fda57433d9a278dbc974150377b20f155ceb99d3acce`。
  SDK llvm-readobj --notes --dyn-symbols原始readobj.log hash
  `7ca6496a5e67d6f1c46ca98fed9ed1f016b80e2ead20d58c06e18305fb1dcc35`。
- 绑定kernel111283974255600：gfx1100、wavefront_size32、固定共享128字节。
  唯一非空动态未定义符号为__nvvm_shfl_sync_bfly_f32；rsqrt已无未解析符号。
  OCML控制常量也进入产物；不代表其wave64常量与实际wave32完全相容，仍需闭包核查。
- 解释：固定SerializeToHsaco.cpp按__ocml_前缀触发设备库链接，这条既有路径
  现在有真实产物证据。没有测试math.rsqrt前端自动恢复，不能将API声明叫作恢复。
- 未执行：GPU加载、数值/性能、完整host链接；不声称与CUDA rsqrtf数值等价。
  原始adapter及固定编译器不改，不是等资源基线或新的代码谱系。
- 下一步：限定full-mask/logical32/收敛前提的shuffle兼容诊断及独立路由检查；
  若普通映射即可打通，应如实作为强基线，不当作WaveBridge算法贡献。
