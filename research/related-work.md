# 相关工作核实清单

以下链接均由用户提案提供。本次仅保留研究线索，未独立核实全文、版本、工具行为或会议状态。所有能力差异仍为待核实。

| 工作 | 对照问题 | 核实状态 |
| --- | --- | --- |
| [SCALE warp size](https://docs.scale-lang.com/stable/manual/library/warpsize/) | 正确兼容模式的实际开销、native 诊断和适用条件 | user_provided_unverified |
| Polygeist：Retargeting and Respecializing GPU Workloads for Performance Portability | 显式 shuffle/ballot 下能否保持输出关系并重新分工；需补正式来源/实现版本 | user_provided_unverified |
| [Triton Linear Layouts](https://arxiv.org/html/2505.23819v1) | 可复用布局表示与我们所需关系恢复的边界 | user_provided_unverified |
| [CKTI](https://dl.acm.org/doi/10.1145/3797905.3800551) | CUDA 到 Triton IR 的具体子组覆盖；全文/实现访问待核实 | user_provided_unverified |
| [GPURepair](https://link.springer.com/chapter/10.1007/978-3-030-67067-2_18) | 同步/竞争修复与输出计算关系检查的具体边界 | user_provided_unverified |
| [Mirage](https://www.usenix.org/conference/osdi25/presentation/wu-mengdi) | 其等价验证范围与本项目跨线程组织检查的联系 | user_provided_unverified |
| [CASS](https://arxiv.org/html/2505.16968v4) | 转译中的硬编码宽度/intrinsic 支持 | user_provided_unverified |
| GEAK / AMDKernelVault | AMD agent 生成和迁移能力；需补一手来源 | user_provided_unverified |
| [rocPRIM warp reduce](https://rocm.docs.amd.com/projects/rocPRIM/en/latest/warp_ops/reduce.html) | 逻辑分组语义和正确兼容实现 | user_provided_unverified |
| [MLSys CFP](https://mlsys.org/Conferences/2027/CallForResearchPapers) | 投稿范围与评审要求；提交前复核当届条款 | user_provided_unverified |
| [FlashInfer-Bench](https://proceedings.mlsys.org/paper_files/paper/2026/hash/37e44c4b5321605735be9761f9b758fc-Abstract-Conference.html) | 真实工作负载、正确性评估与系统接入的方法 | user_provided_unverified |

后续每项能力记录至少包含：访问日期、一手来源/页码、代码版本、共同输入、运行命令、结果、限制，以及事实与推断的区别。无法获取资料就保留未知。
