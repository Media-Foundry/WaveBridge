# 编译器接入边界（待实现）

这里将承载真实 HIP/CUDA 源码语义分析与变换。当前没有 C++ 编译器实现或构建目标；Python qdot fixture 不能作为已经实现源码分析的证据。

| 子目录 | 第一项交付 | 主要接口 |
| --- | --- | --- |
| `frontend/` | 一个固定工具链下的编译数据库/入口/launch 提取器 | SourceBundle |
| `ir/` | 由真实案例驱动的关系表示和文本 dump | RelationArtifact |
| `analysis/` | lane/group、collective 依赖与输出归属的受限联合恢复 | 关系、前提与拒绝原因 |
| `verification/` | 明确源/目标语义的关系检查义务与证据 | CheckEvidence |
| `transforms/` | 绑定 kernel/launch 的协作宽度变换 | CandidateBundle |

具体 LLVM/Clang 版本、MLIR/Polygeist 复用方式和第三方依赖在 G1 后用 ADR 固定。初始接入应通过可版本化工件或稳定命令行边界与 Python 编排连接，不在当前没有使用者时引入绑定层。
