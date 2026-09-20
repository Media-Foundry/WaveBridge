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

## 尚未完成

- HIP/CUDA 源码关系恢复与通用关系 IR。
- 通用跨 lane checker、ballot/掩码/共享内存/浮点协议支持。
- Clang/LLVM 集成、目标代码生成及模型到生成代码的一致性检查。
- 设备能力探测、实际 wave32/wave64 验证、正确兼容 fallback 与 GPU runner。
- 真实 kernel 语料、Polygeist/CKTI 共同案例验证、强基线复现。
- 性能数据、端到端部署、人工成本数据、创新性结论和论文结果。

## 验证记录

2026-09-20 的本地验收（Python 3.12.7）：

- `make check`：42 项 CPU 测试通过，另包含 40 组行列边界组合的子用例。
- `make demo`：32→64 模型候选获得 `checked`，量化分组保留为 32，grid 从 2 更新到 3。
- `python3 -m pip wheel --no-deps --no-build-isolation .`：wheel 构建成功。
- 在独立临时虚拟环境安装 wheel，离开源码目录并清除 `PYTHONPATH` 后执行 `wavebridge demo`：成功。
- 全仓 JSON/TOML 解析、Markdown 相对链接和尾随空白检查：通过。

本地验证不代表 GPU 正确性或性能。没有执行 GPU 实验；GitHub Actions 的实际状态以对应提交的运行记录为准。

## 下一项研究任务

依照 `research/differential-cases.md` 纳入一个许可清楚、来源固定的真实 kernel，人工标出跨 lane 关系并设计错误变体。检查 Polygeist/CKTI 的实际能力后，再决定源码恢复的首个支持子集。
