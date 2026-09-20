# ROCm 后端前提与实际门控

- 日期2026-09-20，分支 `wb03-source-ast`，基线 `f574a09`；中文回复，
  直接本地commit，不创建PR、不推送。
- 主代理执行字段审计、运行库符号及设备bitcode读取；Sol只读核查后端配置。
  原上游/前端构建配置保持不变，未启动第二个大型构建或GPU。

## 字段审计

在前轮兼容wrapper的独立副本中增加type_traits和两项宏内断言：每个实际
复制字段的 `sizeof` 相同且 `std::is_same<decltype(...)>` 成立。
`artifacts/polygeist-property-audit-U3fpkU/RocmRuntimeWrappers.cpp` 包含42个
实际宏调用，原注释字段不计入。固定Clang16 `-fsyntax-only -std=c++17` 与
同组HIP/CUDA头编译退出0，完整命令在compile.log；无运行时调用。

| 工件 | SHA-256 |
| --- | --- |
| 审计CPP | `7e9d178b8fc108a2afbc0c73dd576b724d294172e987569a603c2c20a07e2e83` |
| compile.log | `fb39e481771077e66fa7d58cc97ed374b1d34a3085b1a181c2c9e6d8fb89e37c` |
| `experiments/baselines/patches/rocm-wrapper-property-audit.patch` | `35fac684276cd56deb1da8b1799ae2d81f69bee937ec57762d1e4a31ffdfbb76` |

前轮完整wrapper的LL引用 `hipGetDevicePropertiesR0600`；主代理实际
`readelf --dyn-syms --wide <SDK>/lib/libamdhip64.so.7` 确认该函数以hip_6.0
版本导出。仅证明名称存在与字段编译类型，不证明整个调用ABI、字段值含义、
未映射字段初始化或失败分支安全；不据此部署属性适配函数。

## 设备库实际失败

执行固定Clang16 `-S -emit-llvm <SDK>/lib/llvm/amdgcn/bitcode/ocml.bc
-o artifacts/polygeist-property-audit-U3fpkU/ocml.ll`，退出1：

```text
Unknown attribute kind (106) (Producer: 'LLVM23.0.0git' Reader: 'LLVM 16.0.0git')
```

日志 `device-bitcode-read.log` SHA：
`b16051e8c7393320ff4415e4e5785f4afb33e8f9b05cfa98cc03a71a621ec7f3`。
输入ocml.bc SHA：`7b0d1bc455ec41ad461b688f404c211a12b880e36ff74eb8061e97502464bae8`。
这是真实bitcode读入不兼容，不是GPU kernel语义失败。

## 独立完整构建的配置依赖（尚未配置）

- LLVM需host与AMDGPU targets；Polygeist启用ROCm。无需启用MLIR ROCm runner，
  后者会引入额外设备探测和依赖。
- Polygeist两处find_package(hip)，实际消费target为Passes的hip::host。
  当前SDK缺vendor hip-config；可显式导入已验证include/runtime，但必须标注
  自定义发现模块，不能伪造vendor版本、设备能力或完整开发包。
- wrapper要求固定Clang的typed-pointer bitcode，已完成编译诊断；完整构建
  如使用兼容补丁，必须是独立patched源目录，不称未修改论文工件。
- SerializeToHsaco从显式rocm-path/amdgcn/bitcode载入设备库，并调用
  rocm-path/llvm/bin/ld.lld；当前SDK布局不同，需要独立路径视图。
- **先准备LLVM16可读且目标适用的设备库**。路径存在不代表兼容；此次失败
  已排除直接使用现有LLVM23 ocml。不能只为构建通过删除设备数学库或改算法。

验收：真实编译与bitcode读取、readelf、审计patch dry-run及diff-check。
只新增诊断patch/记录，未重跑既有282项测试。G1未通过，完整GPU后端、shuffle
最终映射、数值及性能仍无结果。
