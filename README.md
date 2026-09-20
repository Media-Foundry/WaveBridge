# WaveBridge

WaveBridge 面向既有 ML kernel 中的显式子组通信，研究跨 lane 数据依赖和输出归属的恢复，以及改变协作宽度时的关系检查。

当前阶段是**可运行参考模型、设备探测、真实 kernel 手工基线与 Clang AST 接入**。尚未实现 HIP/CUDA 源码关系恢复、GPU 候选代码生成或性能评测；创新性仍待与 Polygeist、CKTI 等工作逐例对照。参考模型的检查结果不能用作真实 kernel 正确性的证明。

## 快速开始

需要 Python 3.11+；本地检查仅使用标准库，不需要 GPU、网络或额外依赖。

```bash
make check
make demo
PYTHONPATH=src python3 -m wavebridge inspect examples/qdot/source.json
PYTHONPATH=src python3 -m wavebridge check examples/qdot/source.json examples/qdot/logical64.json
PYTHONPATH=src python3 -m wavebridge check examples/qdot/source.json examples/qdot/wrong_quant64.json
```

WB-01 的设备探测入口为 `python3 runtime/probes/probe.py --hipcc /path/to/hipcc`，需要 HIP 开发工具链及可用设备，详见 [探测协议](runtime/probes/README.md)。CPU 测试不触发 GPU 执行。本机 W7900 的普通 wave32 探针已通过编译元数据与运行行为核对；这不代表任意 kernel 已验证。

WB-02 的 [llama.cpp RMSNorm 案例](benchmarks/cases/llama-rmsnorm/README.md) 提供固定来源、手工提取的 logical32 基线及独立 reference；W7900 上 9 个确定性输入通过冻结数值协议。它不是自动适配，也没有跨波宽或性能结论。

最后一条命令故意检查错误候选，返回 `rejected` 和退出码 1。`checked` 返回 0，`unknown` 返回 2，输入或命令错误返回 3。检查报告以 JSON 输出，包含模型哈希、数值语义、适用范围和诊断。

可选安装：`python3 -m pip install --no-build-isolation -e .`，随后使用 `wavebridge demo`。

## 仓库导航

```text
AGENTS.md                  中文回复与全仓工程/证据规则
.agents/                   角色边界、执行流程、任务与交接模板
docs/                      架构、协议、当前状态、决策记录、阶段门槛
src/wavebridge/             Python 参考模型、检查、候选生成与 CLI
compiler/                   后续 Clang/LLVM 源码分析与变换的接入边界
runtime/                    最小 HIP 设备探测器；通用执行与 fallback 待实现
examples/qdot/              量化点积的结构化模型与错误候选
tests/                     CPU 语义回归和命令行集成测试
benchmarks/                 真实语料纳入协议、谱系拆分、基线定义
experiments/                实验协议、设备模板、结果记录格式
research/                  候选主张、相关工作核实、差异验证案例
artifacts/                 本地产物（默认不入版本控制）
.github/workflows/          CPU 测试、演示和包安装检查工作流
```

参考模型沿着 `frontend → ir → analysis / verification → transforms → pipeline` 组织。它针对固定形状、无界整数的量化点积，显式模拟 guarded shuffle-down 和唯一输出写入者，检查加乘表达式及重复计数。输入模型是人工提供的，不是从源码恢复的。

源模型使用 32 个 lane 协作，候选使用 64 个 lane；数据格式中的量化分组仍是 32。将量化分组误改成 64、漏掉 collective 阶段、重复累计或遗漏输出都会被对应测试覆盖。逻辑协作宽度和物理波宽保持独立，参考模型不模拟真实 HIP intrinsic。

详细入口：[架构](docs/architecture.md)、[协议与保证范围](docs/contracts.md)、[当前状态](docs/status.md)、[路线图](docs/roadmap.md)、[协作约定](.agents/README.md)。项目尚未选择开源许可证；引入第三方代码前必须记录来源和许可。
