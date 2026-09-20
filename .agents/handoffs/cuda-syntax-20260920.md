# CUDA 前端检查交接

- 日期：2026-09-20；分支 `wb03-source-ast`；父提交 `61fcbf0`。
- 目标：让同例人工 CUDA 输入实际经过编译前端，不把环境问题当先前工作能力差异。
- 输入源码未修改；`cuda-port.json` 更新为仅 host/device 语法通过，
  `cuda-syntax-evidence.json` 索引两份成功、四份失败的本地原始报告。
- 成功命令使用 AOCC Clang 17.0.6、`-fsyntax-only`、`sm_70`、真实 NVIDIA 头文件。
  两侧退出码均为 0，保留 CUDA 12.1 partially supported 警告。
  没有代码生成、链接、GPU 执行、数值比较或自动恢复。

## 本地依赖与复现

依赖只放在 `artifacts/toolchains/`，不修改全局 SDK、不使用伪造头文件。
安装命令分别为：

```bash
python3 -m pip install --target artifacts/toolchains/cuda-12.1-wheels --no-deps nvidia-cuda-runtime-cu12==12.1.105 nvidia-cuda-nvcc-cu12==12.1.105
python3 -m pip install --target artifacts/toolchains/curand-10.3.2.56-wheel --no-deps nvidia-curand-cu12==10.3.2.56
git clone --depth 1 --branch 1.9.0 https://github.com/NVIDIA/libcudacxx.git artifacts/toolchains/libcudacxx-1.9.0
```

libcudacxx HEAD 已核对为 `538a6a57bb155ea7a0a5d8371b7b5480b5a963f1`。
版本选择参考 [CUDA 12.1 官方组件表](https://docs.nvidia.com/cuda/archive/12.1.0/cuda-toolkit-release-notes/index.html)。
已安装但未用于成功命令的 CCCL 12.1.55 wheel 缺 `nv/target`，不能当完整 SDK。

新建的本地 `cuda-view-Zt5WBj` 只包含三个符号链接：

```text
include -> ../cuda-12.1-wheels/nvidia/cuda_runtime/include
bin     -> ../cuda-12.1-wheels/nvidia/cuda_nvcc/bin
nvvm    -> ../cuda-12.1-wheels/nvidia/cuda_nvcc/nvvm
```

在仓库根目录执行以下命令（重新运行须换全新输出路径，禁止覆盖原报告）：

```bash
for cuda_mode in host device; do
  PYTHONPATH=src python3 -m wavebridge.frontend.clang_ast \
    benchmarks/cases/llama-rmsnorm/baseline/rmsnorm_logical32.cu \
    --compiler clang++ --compiler-arg=--cuda-${cuda_mode}-only \
    --compiler-arg=--cuda-path=artifacts/toolchains/cuda-view-Zt5WBj \
    --compiler-arg=-isystem --compiler-arg=artifacts/toolchains/cuda-12.1-wheels/nvidia/cuda_nvcc/include \
    --compiler-arg=-isystem --compiler-arg=artifacts/toolchains/curand-10.3.2.56-wheel/nvidia/curand/include \
    --compiler-arg=-isystem --compiler-arg=artifacts/toolchains/libcudacxx-1.9.0/include \
    --compiler-arg=--cuda-gpu-arch=sm_70 --compiler-arg=-std=c++17 \
    --symbol rms_norm_f32_logical32 \
    --output artifacts/cuda-common-input-01/${cuda_mode}-sdk-view.json || exit
done
```

命令、原始诊断、AST、源码和编译器哈希保存在各报告中。索引只有部分入口头哈希，
不是完整依赖锁定或公开复现包。CPU 测试不代替上述实际编译。

## Polygeist 前提

本地主代理已完成 detached checkout：
`artifacts/toolchains/polygeist-cgo24` HEAD 为
`ba9953a08c9bc0965090911b67b2b1e1778cbb59`，工作树干净。
`git submodule status llvm-project` 为未初始化的
`0b9310c6e4416ee48c07edfef81144e22850dfe7`。
Sol 只读核查构建依赖；现有已检查 SDK 路径没有匹配 MLIRConfig，不能直接构建。
下一步取得并核对精确 LLVM 子模块，建立 cgeist；尚无共同案例转换结果。
不把在父仓库查询子模块对象失败当作子模块远端不可用证据。

本轮直接本地 commit，不 PR、不推送；G1 和完整自动适配均未完成。
主代理验收：`make check` 251 项通过，`git diff --check` 通过；
用 `jq` 提取索引后送入 `sha256sum --check`，六份本地报告全部一致。
