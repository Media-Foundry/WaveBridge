# 交接：源码列标签与形式覆盖

- 日期、分支和基线：2026-10-15，`wb03-source-ast`，基线`7cefc5a4212133eaca853121e1aa4947645e0e39`。
- 用户目标与中文约定：持续推进真实源码适配门控；始终中文，直接commit并定期push，不创建PR或合并master。
- 已完成：`column_coverage.check_fixed_guarded_labels`连接fresh普通嵌套入口、真实typed仿射标签、严格小于guard和count保持；逐运算signed范围及精确声明绑定。新真实Clang/CPU回归8项。架构、接口、状态和实录已同步。
- 真实重放：完整冻结HIP守卫候选AST，最终报告`artifacts/wb-fixed-labels-20261015-01/report-final.json`，退出0、82.051秒，条件checked；W=32，K=4，标签[0,127]，共同n的支持域[0,128]。实现前后哈希一致，raw报告SHA256 `437aa32da9c4d544341f29deffdb60f36db480ca31dacaf681e4c9aba7094699`。
- 实际验收：最终Clang17/23各8项通过，无跳过，耗时6.594/6.174秒；日志同目录`clang17-final.log`、`clang23-final.log`。demo/diff通过，Sol只读复核无阻断。首轮全量1411项464.359秒通过；补明count独立间接别名前提和报告断言后，最终全量1411项459.779秒通过，无跳过，日志`check-final.log`。全部为本地验收，未核验本提交的远端CI。
- 失败记录：首版合成CPU计数fixture的else会清零累积结果；仅计数fixture改为空else。失败`unit-final.log`保留，修正后的7项`unit-corrected.log`及最终8项日志分开。真实HIP未改动。
- 保证范围：只对每个固定outer row的完整形式lane×iteration族与共同n给出标签一次覆盖。实际参与、count入口域/跨lane相同、指针历史、load覆盖/source/deploy未建立；leaf域、builtin效果及count独立间接别名前提仍为外部假设，host配置未fresh组合。
- 没有执行：GPU、kernel数值/性能、native64变换、完整配置→load覆盖验收。历史GPU基线没有升级保证。大AST与原始报告为本地ignored产物，未上传完整复现包。
- 版本交付：本交接与实现归为同一提交，直接推送当前工作分支；最终同步状态以git核对为准，不包含ignored大工件。
- 下一项：检查同一行count域/共同性及实际load下标和形式标签的对应，fresh组合配置链；保持参与、地址有效性与加载值义务分开，不继续堆独立getter报告。
- 下一项源码选点提示（仅阅读观察，未由checker建立）：冻结`PersistentSoftmax.hip.cuh`中`src += first_batch*stride+local_idx`发生在双循环前；guard使用`local_idx+it*WARP_SIZE`，实际读取是`src[i*element_count+it*WARP_SIZE]`。不能忽略前缀pointer调整，也不能把`i*element_count`自行改读为`i*stride`；两者对应需真实launch/输入协议。count初始化为`i>=local_batches ? 0 : element_count`。
- 阻塞：当前无新增用户输入需求；复现命令、哈希和外部协议见`experiments/hip-fixed-labels-20261015.md`。
