# 交接：完整 ROCm 构建与首个真实代码工件

- 日期/分支/基线：2026-09-20，wb03-source-ast，f5f5a3d；中文，直接commit，不PR/push。
- 原构建session29377已3895/3895退出0。不要继续poll或重新启动完整构建。
  路径`artifacts/toolchains/polygeist-rocm-build-02`，配置/patch来源沿用构建交接。
- 实际SHA256：
  - bin/cgeist：`ef5fb79acf82db9ebcdcdadf5d0a35d0eb89615bbc0896eccb5f8266918ad054`
  - bin/clang：`18d3a1eaa5987b96b26b065497ad083bbf945784ad6f9ba10836603f5c11bf07`
  - bin/ld.lld：`c9794644e4241617a67a172d49075db62e871030cecc325973d574955b8d83e6`
  - build.log：`f2f572a170a43b50c8b5ac8bf0998f977d1617e5ffec8fed04a190ee05cacd0d`
  - tools/polygeist/lib/polygeist/ExecutionEngine/RocmRuntimeWrappers.cpp.bc：
    `4e6b8f238f9c6ad4716bc89def1552602447f5efb48616f6ad1e9980e04b08a8`
- 首次实际运行`artifacts/polygeist-frontend-29q5vvu0/report.json`退出127，
  loader缺libamdhip64.so.7，不是kernel语义失败。未改SDK或构建缓存。
- 后续命令环境显式设置：
  `LD_LIBRARY_PATH=/home/husrcf/anaconda3/lib/python3.12/site-packages/_rocm_sdk_core/lib`
  与`PYTHONPATH=src`。该继承环境尚未自动写入runner报告，必须保留本记录。
  使用polygeist_frontend.py、新build cgeist/resource-dir、原CUDA11.8/GCC11 includes、
  rocm-backend-view-01、gfx1100、sm_70及默认function=*，不启用cuda-lower。
  报告保存完整argv/cwd/stdout/stderr，记录器设置不可见设备掩码；掩码不是沙箱。
- GPU MLIR报告`artifacts/polygeist-frontend-ms6figcb/report.json`：退出0，
  hash `b9a04895cd390cc021197a68bc2626456282b18e594b51b94aed046bd808f4e7`；
  output.mlir hash `f2a5d23f8e26fa443f58f82bf8507185fc1b1c33cce6e58b76e9f7079828dc24`。
  实际有gpu.module/gpu.func/host launch_func、ROCDL barrier、两次shuffle call；
  无polygeist.alternatives，仍是外部shuffle和memref<1xf32,3>共享全局。
- 加`--emit-llvm`报告`artifacts/polygeist-frontend-jo4d2x3t/report.json`：退出0，
  hash `d381ebf2913896de581ba11a4f944a4fa175b37f51e3cd2887e50d40ab2a47b2`；
  output.ll hash `52da2d365f96a1748219915cf4073767b9b7980435cd833ddca957e8c153fe2d`。
- 同目录extract_binary.py严格匹配单个GPU binary global、解码LLVM转义并检查长度/ELF；
  首次因未覆盖双反斜线转义而拒绝，补齐后提取7928字节embedded.hsaco，hash
  `cc36e19f48bc6093fcda2e3c8a6b0429c654151e1e19983765ad931d8483fd09`。
  这是诊断脚本，不是通用解析器/验证器，不执行二进制。
- GNU readelf与SDK llvm-readobj交叉确认两个动态未定义符号：
  `__nvvm_shfl_sync_bfly_f32`、`__nv_rsqrtf`。readobj原始结果在同目录readobj.log。
  llvm-readobj使用SDK的lib/llvm/bin版本，仅解析ELF，不用于编译或设备bitcode链接。
- 元数据绑定kernel111387597296336：target gfx1100，wavefront_size32，
  group_segment_fixed_size4；host LLVM第182行mgpurtLaunchKernelErr传smem=0。
  原源码需要多组共享值；当前产物不能放行。波宽仅是静态产物证据。
- 没有执行：GPU加载、数值测试、性能测试、完整host链接、静态shared副本后端检查。
  未解析符号没有已验证提供者，不假设运行时能解决，也不声称已实测加载失败。
- 下一步：相同工具/环境运行已固定静态shared诊断副本的两阶段；检查共享容量
  是否变为128字节及未解析符号是否仍在，分离局部问题。不要把普通lowering补全
  本身包装成跨lane关系分析的创新；G1和源码→自动适配→GPU闭环仍未完成。
