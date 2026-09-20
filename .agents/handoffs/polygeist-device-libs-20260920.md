# LLVM16 兼容设备库

- 日期2026-09-20，分支 `wb03-source-ast`，基线 `e84541b`，开始工作区干净。
- 中文回复，直接本地commit，不创建PR、不推送。主代理实际获取/构建/验证，
  Sol只读核查gfx1100及ABI400源码入口。

## 固定输入与首次失败

官方 `https://github.com/ROCm/ROCm-Device-Libs.git` 无rocm-5.3.4 tag；实际
ls-remote显示5.3.0～5.3.3均解引用到 `cc06f7066f8fc9d963985cc70d8dd6fc12eafe1d`。
以5.3.3固定克隆 `artifacts/toolchains/rocm-device-libs-5.3.3`，原工作树干净。
这不是Polygeist论文5.3.4环境的精确复现。

同固定LLVM构建补齐 `llvm-link opt`，7任务退出0。设备库初次独占构建
`rocm-device-libs-build-1UvK9c` 配置成功，但prepare-builtins用C++14遇到LLVM16
头的C++17类型错误；build.log SHA为
`a23da4c5242c70829a85d0892e8fe932f3717ba6c8c7c4701d11ff5b5a019170`。
原失败保留，未修改原checkout。

独立worktree `rocm-device-libs-5.3.3-cxx17` 仅修改该工具CXX_STANDARD 14→17。
已提交patch SHA：`26ef476d3d1050861bf22a3b11460b654c9a3adb45a8a747cda365ecf250b97f`。
设备代码未改。第二次还禁用非必需ROCM包发现，避免引入系统ROCm配置模块。

## 成功构建

完整命令在 `artifacts/toolchains/rocm-device-libs-build-A96OBY/configure.log`：
系统 `/usr/bin/cmake` 3.28.3、Ninja、Release，CMAKE_PREFIX_PATH指固定LLVM16
build02，C/CXX编译器均指其clang，`CMAKE_DISABLE_FIND_PACKAGE_ROCM=ON`，
`CLANG_OPTIONS_APPEND=-Xclang;-no-opaque-pointers`。
采用CMake3.28是因为上游明确设置旧CMP0053策略，不改上游策略代码。

`cmake --build <build> --target opencl ocml ockl --parallel 8` 547任务退出0。
下面三份库用同版opt `-opaque-pointers=0 -passes=verify -disable-output` 分别
通过，再用同版llvm-link `-opaque-pointers=0` 联合链接并verify通过。
没有覆盖输入库，合并产物为 `combined-reader-check.bc`，不替代正式三个库。

| build-A96OBY内工件 | SHA-256 |
| --- | --- |
| `amdgcn/bitcode/opencl.bc` | `e550ae39782180843a42f96d36cc5de6291a9f30a52f9e7b5e07c489a8cb3312` |
| `amdgcn/bitcode/ocml.bc` | `103b1a981ffddee5d06210aa0d06e40c9f6271782b89500f57864cb645861967` |
| `amdgcn/bitcode/ockl.bc` | `759632fd3edb3bd0440a06be802029d89ae53100e86d75a0b29de5c7f017e9ca` |
| `configure.log` | `eae97521b08fbf78edec743cf2b06ddc7c41baa17a24780a1884b75fcbc5f7f7` |
| `build.log` | `35522836398c70349ddbe8cdc3c54b6cd448516d71cedb475bf7112d59fd9840` |
| `reader-check.log` | `b9fb1b6344079072f0690273482403fc1464a6988bb371ec41c2036b51a5fb8f` |

## 边界与下一步

源码控制库包含ISA11000和ABI400/500入口；这只支持继续测试gfx1100，不证明
最终目标代码适用。此次仅构建三项必要设备库，未构建所有控制库或执行上游
完整测试。Polygeist会自行注入控制常量，仍须核实其wavefront/ABI与目标一致。

后续可配置独立patched Polygeist ROCm后端，使用兼容设备库与同版lld；原
frontend-only配置不改。GPU链接/HSACO、shuffle映射、数值和性能均未建立，
G1仍未通过。本轮无核心实现变更，未重跑既有282项CPU测试；实际验证为设备库
构建、逐库/合并IR verifier、哈希、原树干净及diff-check。
