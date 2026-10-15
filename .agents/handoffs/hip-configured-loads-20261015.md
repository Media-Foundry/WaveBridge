# 交接：Host配置到选定加载地址

- 日期、分支和基线：2026-10-15，`wb03-source-ast`，基线`a1011f8a0e5c2a5dfe760ec42fa911b4023d980d`。
- 用户目标与语言：持续推进真实源码适配门控；始终中文，直接commit并定期push，不创建PR、不合并master。
- 完成文件：block_configuration新增check_guarded_coordinate_to_fixed_loads，fresh配置派生leaf域到完整加载检查；普通内层入口原有身份/哈希连接抽成共享私有函数，旧API范围不变。独立native CUDA fixture及新组合测试、架构/接口/状态/实录同步。
- 分工：GPT-5.6 Sol实现两份独立测试/fixture，并只读复核生产入口，未发现阻断；主代理完成实现、完整HIP重放、统一验收及版本交付。
- 实际验证：旧配置16项202.096秒通过（existing-config.log）；新组合5项99.222秒通过（工具输出转存tool-session.txt，非shell原生日志）；demo/diff通过。完整HIP重放退出0、695.167秒、条件checked，运行前后实现哈希一致；最终全量1428项628.887秒、退出0、无跳过（check.log）。目录artifacts/wb-configured-loads-20261015-01/。均为本地验收，未核验本提交远端CI。
- 真实结果：配置(32,4,1)派生lane域[0,31]，同次22个静态配置copy的条件保持检查连接到load地址`row_at_snapshot*stride_at_snapshot + outer*n + column`。报告SHA256 `b7320e27c207591cde771c93d0961177df7f7a3f986ab3d90b9d209dc3de290d`；source/deploy保持false。完整分析耗时不是GPU性能数据，未做热点归因。
- 保证边界：不读旧成功结论、不手填leaf域；count/row/stride仍为外部窗口。API/runtime、noalias、call effect/normal return等前提保留。共同count、实际线程参与、完整内存覆盖、分配/指针表示、输入内容/目标后续保持和source/deploy仍未建立。
- 未执行：GPU、数值/性能、native64变换、机器码/原始生产TU验证；旧GPU结果未升级。大型AST和原始报告为本地ignored工件，不称公开完整复现包。
- 版本交付：已验收实现、测试和本交接归为同一提交，推送当前工作分支；最终同步以git核对为准，不包含ignored大工件。
- 下一项：源码first_batch由blockDim.y、blockIdx.x、threadIdx.y与WARP_BATCH形成；local_batches由batch_size减去first_batch并限幅；inner count是i与local_batches比较后选择0/n。应按固定x族检查这些来源与共同性，不能仅由count的区间或readonly断言推导跨lane相同。
- 阻塞：无新增用户输入需求；持续目标保持active，不将局部组合里程碑当作全部研究完成。
