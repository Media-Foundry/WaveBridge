# RMSNorm 共同案例：先前工作核查

核查日期：2026-09-20；本仓基线 `bb575ef`。使用 research-lit 工作流做定向
检索，无本地论文库或可用 Zotero/Obsidian；arXiv 脚本缺失，改用站点限定检索，
未找到这两项工作的额外匹配预印本入口。未保存论文副本或下载完整 benchmark 包。

## 文献与方法定位

| 工作 | 发表 | 方法与作者报告结果 | 对当前案例的意义 | 本轮一手来源 |
| --- | --- | --- | --- | --- |
| Ivan R. Ivanov、Oleksandr Zinenko、Jens Domke、Toshio Endo、William S. Moses：Retargeting and Respecializing GPU Workloads for Performance Portability | CGO 2024，119–132 | 联合thread/block coarsening和调优；作者报告Rodinia几何平均加速27%，不是本仓复现 | 已覆盖旧CUDA工作重分配、kernel/launch联合修改，不可将这些直接当作差异 | [作者论文](https://c.wsmoses.com/papers/polygeist24.pdf)，第1、3页及artifact appendix；[归档](https://zenodo.org/records/10465934) |
| Changqing Shi等：CKTI: A Domain-Specific Compiler for Lowering CUDA Kernels to Triton-IR | ICS 2026，ACM | 本轮只核实题名、作者和出版元数据；未取得全文，不报告算法或性能数字 | 仍是直接对照对象；子组通信覆盖未知 | [出版方登记的Crossref元数据](https://api.crossref.org/works/10.1145/3797905.3800551)，[DOI](https://doi.org/10.1145/3797905.3800551) |

Polygeist论文的输入是CUDA，输出面向CUDA/ROCm，且保留host/device联合变换。
本轮核实了artifact所指的旧版本，而非用当前默认分支替代论文实现。附录要求
精确LLVM子模块，并列出Clang 16、ROCm 5.3.4及CUDA依赖；本机已有HIP 7系SDK
不能被默认为同一构建环境。[来源：论文附录D–F](https://c.wsmoses.com/papers/polygeist24.pdf)

本轮源码阅读只确定了入口位置：归档版本的 `CGCall.cc` 中shuffle特判位于
注释块内，之后仍有GPU、builtin与普通调用处理。因而，“搜到unhandled字符串”
和“未搜到目标intrinsic名字”都不能证明该工具无法编译或变换本例。需要构建后
观察实际输入、IR、变换与目标结果。[固定版本源码](https://github.com/llvm/Polygeist/blob/ba9953a08c9bc0965090911b67b2b1e1778cbb59/tools/cgeist/Lib/CGCall.cc#L555)

CKTI的ACM摘要/全文入口本轮访问失败，Crossref响应没有摘要或全文链接。
GitHub仓库搜索 `CKTI compiler` 返回0项，只能记录这次检索未定位实现，不能
推断实现未公开或不支持RMSNorm。其技术能力仍为unverified。

因此G1仍未通过。本仓已有HIP手工提取基线，但它不是已准备好的共同CUDA输入；
不能把HIP输入接入失败当作CUDA重定向工具的语义不足，也不能用WaveBridge的
局部条件检查与他人的完整执行结果直接比较。本轮没有性能或新颖性结论。

## 固定版本与实际只读检查

- Polygeist：`ba9953a08c9bc0965090911b67b2b1e1778cbb59`，GitHub Git Trees API
  从论文短SHA解析；recursive响应 `truncated=false`。
- LLVM gitlink：`0b9310c6e4416ee48c07edfef81144e22850dfe7`；归档 `.gitmodules`
  指向 `https://github.com/ivanradanov/llvm-project2.git`。
- 实际读取固定提交的raw文件，以Python urllib GET获取，未在本仓vendor源码：

| 文件 | SHA-256 | 阅读所得事实 |
| --- | --- | --- |
| `tools/cgeist/Lib/CGCall.cc` | `975c0d7cbb99ddaf6913c0281d77dfc884a97f7986cfb5695bdeb323b2dddf90` | 558–572为注释；574起依次尝试其他调用处理，448处为builtin处理入口 |
| `tools/cgeist/Lib/clang-mlir.cc` | `35ca92b1d05848d5b66a4b12b8fed63919fbac4f2eb2483c46b35bd27da5df88` | 1878起GPU调用处理，1883–1885有barrier操作构造 |
| `.gitmodules` | `917ddece55ea499305f436b339eba293952da3e2620bb01d4f8ff5a1964d6101` | 指定上述LLVM仓库 |

本机使用 `shutil.which` 查询：`cgeist`、`polygeist-opt`、`nvcc` 均未在当前PATH
发现；`hipcc`、`clang++`、`cmake`、`ninja`在PATH。该结果不等于完整安装盘点，
也不等于缺CUDA头文件。未启动LLVM/Polygeist构建，未执行任何baseline转换。

CKTI查询包括正式DOI的abs/full页面、Crossref works API、网页检索，以及
`https://api.github.com/search/repositories?q=CKTI+compiler`。只能证明本轮访问
与检索结果，不能证明全球不存在其他合法全文或实现入口。

## 同一案例的待执行矩阵

固定来源为llama.cpp `b23efaa2ef147f547ee75cbf0c621d61904de80e` 的
`ggml/src/ggml-cuda/norm.cu`，优先 `rms_norm_f32<256,false,false>`，连续布局、
单channel/sample；现有手工HIP提取源码与补丁在 `benchmarks/cases/llama-rmsnorm/`。

| 对象 | 当前可确认 | 同例运行状态 | 下一项实际验收 |
| --- | --- | --- | --- |
| 正确logical32基线 | 已有W7900的9形状冻结数值记录 | 既有证据；本轮未重跑 | 共同CUDA输入与现有HIP提取的对应关系与补丁 |
| Polygeist论文版本 | 提交、LLVM依赖和公开构建入口已定位 | `not_executed`；PATH无cgeist | 按固定版本构建；先无变换编译，再单独coarsening并保存IR/launch |
| Polygeist较新版本 | 本轮没有固定版本或运行 | `unverified` | 不能用旧版的未来失败断言最新方法能力不足 |
| CKTI | 出版元数据 | `not_executed`；实现入口未定位 | 取得合法全文/实现及版本，再确定共同输入与所需人工修改 |
| WaveBridge | 受限源码分析、条件模型检查、手工GPU基线 | 无自动源码→候选→GPU闭环 | 不将当前条件模型checked记为完整适配成功 |

共同输入必须保留两个阶段的XOR归约、shared partial、barrier与完整launch；
不要先手工换成库归约再称原始模式自动支持。任何为接入而做的语法或API修改需
保存补丁、工时和独立reference核验。按解析、IR、变换、编译、数值与性能分别
记录结果；工具缺失、环境构建失败与语义不支持必须分开。只有共同案例实际执行
之后，才判断是否存在值得研究的额外关系恢复/检查需求。
