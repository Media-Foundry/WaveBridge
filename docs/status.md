# 当前状态

更新日期：2026-09-20。

## 已落地

- 仓库分层、模块依赖规则、协议和设计决策记录。
- 根 `AGENTS.md` 的中文回复约定，`.agents/` 的职责、流程和交接模板。
- 无外部运行时依赖的 Python 包、CLI、严格 JSON 模型输入。
- qdot 固定形状无界整数参考模型，显式 shuffle-down 阶段和输出多项式检查。
- 模型级 32/64 候选生成，kernel/launch 联动，量化分组保持不变。
- 合法/错误候选示例、CPU 回归测试及 GitHub Actions 工作流定义。
- benchmark 来源/谱系/基线协议，实验配置和证据模板，候选主张及相关工作核实表。
- Git 主分支约定为 `master`，origin 指向 `Media-Foundry/WaveBridge`；初始化前确认远端为空仓库。
- WB-01 最小 HIP 设备探测工具：分阶段报告、命令与原始日志、工件哈希、超时与拒绝状态；工具实现不等于硬件门槛通过。
- WB-02 固定 llama.cpp RMSNorm 的完整上游快照、MIT 许可、手工特化补丁、独立 reference、冻结数值协议和隔离的人工 oracle；W7900 上完成有限输入的 logical32 基线实测。

## 尚未完成

- HIP/CUDA 源码关系恢复与通用关系 IR。
- 通用跨 lane checker、ballot/掩码/共享内存/浮点协议支持。
- Clang/LLVM 集成、目标代码生成及模型到生成代码的一致性检查。
- MI250 接入、实际 wave64 验证、正确兼容 fallback 与通用 GPU runner。
- 多谱系真实 kernel 语料、Polygeist/CKTI 共同案例验证、强人工原生基线复现。
- 性能数据、端到端部署、人工成本数据、创新性结论和论文结果。

## 验证记录

2026-09-20 的本地验收（Python 3.12.7）：

- `make check`：42 项 CPU 测试通过，另包含 40 组行列边界组合的子用例。
- `make demo`：32→64 模型候选获得 `checked`，量化分组保留为 32，grid 从 2 更新到 3。
- `python3 -m pip wheel --no-deps --no-build-isolation .`：wheel 构建成功。
- 在独立临时虚拟环境安装 wheel，离开源码目录并清除 `PYTHONPATH` 后执行 `wavebridge demo`：成功。
- 全仓 JSON/TOML 解析、Markdown 相对链接和尾随空白检查：通过。

以上 G0 本地验证不代表 GPU 正确性或性能；当时没有执行 GPU kernel。后续设备探针见下节，GitHub Actions 的实际状态以对应提交的运行记录为准。

## WB-01 / WB-02 首轮门控

WB-01 由一个 GPT-5.6 Sol 子代理实现，主代理负责验收；保留原有 qdot 路径和整数检查范围。

本机 `rocminfo` 可见两个 gfx1100 GPU agent。探测时的 `rocm-smi` 采样显示两卡空闲、无 KFD PID；这只是设备可见性和负载采样，不证明实际波宽。

两条工具链尝试均未执行 kernel：

- 默认 Conda `hipcc`：链接阶段缺少其配置引用的 `libamdhip64.so`，报告 `compile_failed`。
- `/opt/rocm/bin/hipcc`：缺少 `hip/hip_runtime.h`，报告 `compile_failed`。没有安装工具链或混搭 headers/runtime。

上述失败报告保存在本地 `artifacts/wb01-*/report.json`，每次尝试独立记录。它们的 metadata、execute、semantic validation 均未建立，后续成功记录不覆盖这些失败。

最终验收：主代理重跑 `make check`，55 项测试通过（原 42 项和探测器 13 项）；检查通过 `git diff --check`。最终本机报告为 `artifacts/wb01-20260920T065807Z-618484-d01566/report.json`，HIP 源码与 runner 副本哈希均核对一致。CPU mock 状态测试不替代设备执行证据。

继续推进后的 WB-01 实际执行：

- 确认已安装的同一 `_rocm_sdk_core` wheel 中存在匹配的 HIP 7.15.26333 头文件、clang、device libraries 和 `libamdhip64.so.7`，缺的是 unversioned 开发链接名和默认查找布局。
- `prepare_sdk_view.py` 在项目 `artifacts/toolchains/` 建立显式 linker 视图及编译参数；没有安装新包、修改原 SDK 或混用系统和 Conda 的库。
- `HIP_VISIBLE_DEVICES=0` 下 W7900（gfx1100，PCI `0000:53:00.0`）探针成功执行，设备属性、device `warpSize`、ballot、shuffle 与同次编译的具名 kernel 元数据一致为 **32**。
- 最新报告为 `artifacts/wb01-20260920T074250Z-639474-321f6d/report.json`，状态 `verified`；包含源码、runner、SDK view manifest 和二进制哈希。
- 本次通过仅覆盖这张 W7900 的普通 wave32 探针。没有验证 MI250、native64 候选、模型到机器码等价或性能收益。

WB-02 首例实际执行：

- 案例来自 llama.cpp `b23efaa2ef147f547ee75cbf0c621d61904de80e` 的 `rms_norm_f32<256, false, false>`；保留 logical32 XOR shuffle、共享 partial、barrier、第二次归约与广播。standalone 是有完整补丁记录的手工特化，不是自动恢复结果。
- 首次编译因 `rsqrtf` 声明缺失失败，报告 `artifacts/wb02-20260920T074914Z-9daaf0/report.json` 保留。随后显式接入同 SDK 的 HIP math 声明及 Clang wrapper 使用的 OCML 入口；没有改为 `1/sqrt` 或放宽数值协议。
- 同一 W7900、`HIP_VISIBLE_DEVICES=0`，`3×777` 输入全部 2,331 个输出通过；最大绝对误差 `1.1920928955078125e-7`。报告 `artifacts/wb02-20260920T075245Z-3bc452/report.json`。
- 另测 3 行、列数 `1, 31, 32, 33, 255, 256, 257, 1023` 的 8 个确定性输入，均通过。所有比较使用运行前冻结的 `atol=1e-5`、`rtol=2e-5`，epsilon 为 `1e-5`。
- 报告绑定源文件、协议、reference、输入/输出、二进制和 WB-01 证据，并核对运行时设备身份。探针波宽不等同于对 RMSNorm 最终机器码的独立波宽验证。
- 这只证明所测输入的数值通过，不证明整个合法输入域、原上游所有分支、自动源码关系恢复、native64 正确性或性能收益。G1 的先前工作差异仍未建立。
- WB-02 最终本地 `make check`：71 项 CPU 测试通过；包含来源哈希和证据边界回归。设备原始工件保存在本地 `artifacts/`，Git 中的 `benchmarks/cases/llama-rmsnorm/evidence.json` 仅提供索引与哈希，不是完整公开复现包。

## 下一项研究任务

WB-03 已开始源码接入：`frontend/clang_ast.py` 调用真实 Clang，保留多 JSON 根、
函数位置、命令、工作目录及源码/编译器哈希，并区分失败状态。设备视图需显式
`--cuda-device-only`；默认 HIP 可能同时输出 host/device，不能混为单一语义。
本机新入口成功采集 RMSNorm kernel、warp helper、block helper，各一份设备 AST，
报告位于 `artifacts/wb03-ast-J5vhJF/`。源码 SHA 与 WB-02 实测版本一致。
这不读取人工 oracle，但尚未建立常量/调用闭包、launch 对应或跨 lane 关系。
G1/G2 均未因此通过。后续按用户要求直接 commit，不再创建 PR。
本轮 `make check` 81 项 CPU 测试通过，含多 JSON 根、超时日志、非法超时和
禁止覆盖源码/已有工件的回归；没有执行新的 GPU 数值或性能实验。

WB-03 后续增加 `analysis/source_facts.py`：从真实 AST 提取直接调用、声明
引用、运算符和循环，保留源码范围。三个 HIP 函数的结构事实在
`artifacts/wb03-facts-Fnn8eF/`，可见 `__shfl_xor`、`__syncthreads`、helper
和 OCML 调用。`threadIdx.x` / `blockIdx.x` 的 HIP 属性 getter 仍标未知；
没有把仅有引用的 `kLogicalWidth` 猜成常量 32。输入工件哈希与 root index
隔离 Clang ID，不跨编译猜连边。真实 C++ 改名与嵌套间接调用回归通过；
该测试 fixture 不是 ML benchmark，不计入真实语料覆盖。
本轮最终 `make check` 91 项通过，其中 2 项使用本机真实 Clang；没有 Clang
的环境会显式跳过这 2 项，不能把跳过记为真实编译验证。跨 lane 恢复仍未完成。

以首例明确源码恢复的最小支持子集：XOR shuffle、共享内存归约与广播、规则列遍历；先建立源码位置到关系的对应，不扩通用 IR 或调优平台。并行核实 Polygeist/CKTI 对同一案例的能力；尚不能宣布 G1 通过。MI250 接入、WB-03 关系恢复与 WB-04～08 仍待实施。
