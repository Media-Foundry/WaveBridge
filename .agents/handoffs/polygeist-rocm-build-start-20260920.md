# ROCm 后端真实构建启动

- 日期2026-09-20，分支 `wb03-source-ast`，基线 `64155c1`，开始工作区干净。
- 中文回复，直接本地commit，不创建PR、不推送。主代理配置/启动，Sol只读审计。
- **正在运行的真实构建会话为29377**，使用write_stdin继续观察；不要同时另开
  Ninja、覆盖配置或因观察超时重启。配置会话1760已正常退出0。

## 输入和独立目录

- 原Polygeist/LLVM提交不变；新worktree `artifacts/toolchains/polygeist-cgo24-rocm-patched`
  基于ba9953a，仅wrapper增加8行，等于两个既有compat/audit patch叠加。
  CPP SHA为`7e9d178b8fc108a2afbc0c73dd576b724d294172e987569a603c2c20a07e2e83`。
- LLVM source仍指原固定子模块；不修改原frontend-build-02。
- `rocm-backend-view-01/include`指实际SDK头；amdgcn/bitcode指已验证的
  `rocm-device-libs-build-A96OBY/amdgcn/bitcode`，不使用LLVM23设备库。
- view的llvm/bin/ld.lld指新build-02/bin/ld.lld，构建结束前可能是悬空链接。
  cuda-include仅把CUDA11.8 runtime头和同版nvcc的crt以链接聚合，不修改SDK。
- view的lib/cmake/hip/hip-config.cmake是项目自定义映射，非vendor package。
  只声明GLOBAL imported hip::host，绑定实际SDK include、__HIP_PLATFORM_AMD__
  及libamdhip64.so.7；检查文件存在，不声称版本/设备能力或完整HIP包。
  文件SHA：`5e6941ebf28965181341ab85ff5f9fa9d28d4a0c52175d42b25ae3ae23082473`。

## 实际配置与失败保留

首次 `polygeist-rocm-build-01` 因主代理误用不存在的Conda clang路径配置失败；
没有启动编译。重新核实PATH后，在全新 `polygeist-rocm-build-02` 用AOCC
`/opt/AMD/aocc-compiler-5.1.0/bin/clang{,++}`，CMake3.28.3配置成功。
完整命令在该目录configure.log，SHA为
`5f066009e980fc7b8befac42c21e2d9f34de4868709f2785bfe9cfb1d965cd43`。

关键参数：Release/assertions；LLVM projects=clang;lld;mlir，targets=host;AMDGPU；
external Polygeist指patched worktree；ROCm ON/CUDA OFF；MLIR两GPU runner OFF；
显式ROCM_PATH/hip_DIR/CUDA toolkit include；CLANG_TOOL指既有固定LLVM16 clang
用于typed-pointer wrapper，不使用host AOCC或SDK LLVM23生成wrapper。
链接池wavebridge_link=1，LLVM_PARALLEL_LINK_JOBS为空以避免重复pool错误。

构建命令已实际启动：

```bash
/usr/bin/cmake --build artifacts/toolchains/polygeist-rocm-build-02 \
  --target cgeist clang lld clang-resource-headers --parallel 8
```

build.log以pipefail+tee保存set-x命令和原始输出，总任务3895。尚未结束，
不能提前记录二进制hash或成功状态。恢复先确认会话/进程terminal，再按原配置
继续，不重新初始化。原失败配置和frontend产物不删除。

## 下一项验收

完成后核对实际ROCm cgeist、Clang、LLD、wrapper和资源头；显式rocm-path，
从原adapter/静态shared诊断输入分别尝试emit-rocm并检查实际IR/HSACO及shuffle。
先编译不运行GPU；属性适配语义、hardcoded wavefront控制、目标实际模式等仍
未建立。存在SDK版本差异和显式源码补丁，不能称原论文环境精确复现。
此次只记录构建状态，未重跑既有282项CPU测试；G1仍未通过。

Sol只读复核：生成Ninja确有MLIR_ROCM_CONVERSIONS_ENABLED=1及AMDGPU依赖，
wrapper命令与输入hash对应，未发现LLVM23设备库混入。Cache中的MLIR通用
DEFAULT_ROCM_PATH仍为/opt/rocm，因此运行时必须显式传上述backend view，
不能依赖默认路径。patched worktree仍在上游HEAD，补丁是工作树diff而非新
上游commit。主代理末次轮询会话29377仍活跃，推进至351/3895，无terminal结果。
