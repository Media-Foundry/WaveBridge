# WaveBridge

WaveBridge 面向既有 ML kernel 中的显式子组通信，研究跨 lane 数据依赖和输出归属的恢复，以及改变协作宽度时的关系检查。

当前阶段是**架构与可运行参考模型**。没有实现 HIP/CUDA 源码分析、GPU 代码生成或硬件评测；创新性仍待与 Polygeist、CKTI 等工作逐例对照。参考模型的检查结果不能用作真实 kernel 正确性的证明。

## 快速开始

需要 Python 3.11+；本地检查仅使用标准库，不需要 GPU、网络或额外依赖。

```bash
make check
make demo
PYTHONPATH=src python3 -m wavebridge inspect examples/qdot/source.json
PYTHONPATH=src python3 -m wavebridge check examples/qdot/source.json examples/qdot/logical64.json
PYTHONPATH=src python3 -m wavebridge check examples/qdot/source.json examples/qdot/wrong_quant64.json
```

最后一条命令故意检查错误候选，返回 `rejected` 和退出码 1。`checked` 返回 0，`unknown` 返回 2，输入或命令错误返回 3。检查报告以 JSON 输出，包含模型哈希、数值语义、适用范围和诊断。

可选安装：`python3 -m pip install --no-build-isolation -e .`，随后使用 `wavebridge demo`。

## 仓库导航

```text
AGENTS.md                  中文回复与全仓工程/证据规则
.agents/                   角色边界、执行流程、任务与交接模板
docs/                      架构、协议、当前状态、决策记录、阶段门槛
src/wavebridge/             Python 参考模型、检查、候选生成与 CLI
compiler/                   后续 Clang/LLVM 源码分析与变换的接入边界
runtime/                    后续 HIP 执行、目标能力探测与 fallback 的边界
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
