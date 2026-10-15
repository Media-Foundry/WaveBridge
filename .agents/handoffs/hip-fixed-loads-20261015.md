# 交接：选定加载地址、列标签与入口指针历史

- 日期、分支和基线：2026-10-15，`wb03-source-ast`，基线`cb5f566f004d9db69ef50e725952a7d9191f4434`。
- 用户目标与语言：持续推进真实源码适配门控；始终中文，直接commit并定期push，不创建PR、不合并master。
- 完成文件：column_coverage新增check_fixed_guarded_loads，fresh连接标签、guard count来源、实际float load、目标二维数组与入口pointer历史；guarded_stores提取中性私有核心，由旧输出入口和新输入入口共享。新加载组合测试10项，核心额外测试2项；接口、架构、状态与实录同步。
- 分工：GPT-5.6 Sol仅实现guarded_stores核心及对应测试，随后只读复核加载组合，未发现阻断。主代理完成组合、补充负例、统一验收与交付。
- 真实重放：`artifacts/wb-fixed-loads-20261015-01/report-first.json`，退出0、93.230秒，条件checked，Python实现前后不变。报告SHA256 `81c0892ff713fe4fff98e9b59f40a2bd117df8f9c9645287219325a9613d355a`。不裁剪完整HIP AST，不修改真实HIP。
- 结果：地址为`first_batch快照*stride快照 + i*n + column`，W/K/M=32/4/2；n全函数10处只读引用。stride与n不同，不默认相等。目标elements[i][it]，只在所选赋值时成立。
- 实际验证：Clang17/23相关专项各30项、79.172/79.036秒，无跳过通过；demo/diff通过。最终全量1423项518.941秒、退出0、无跳过；日志check.log。命令/哈希见`experiments/hip-fixed-loads-20261015.md`，日志均在上述artifacts目录。这些是本地验收，未核验本提交远端CI。
- 保证范围：外部n入口区间、row/stride快照区间、leaf域、ABI、无写调用/正常返回、既有及保留别名不改保护存储仍为条件；未建立跨lane共同count、实际参与、分配/指针表示、输入内容、后续目标保持、整核/source/deploy。host配置未fresh组合。
- 未执行：GPU、数值/性能、native64变换、机器码或完整生产TU验证。旧GPU基线不升级为本轮结果。大AST和报告是本地ignored工件，未上传为完整复现包。
- 版本交付：本交接与已验收实现归为同一提交，推送当前分支；最终同步以git核对为准，不包含ignored大工件。
- 下一项：在同次调用中连接host配置派生leaf与加载关系，再处理row/count共同性、参与族及加载值对应，不直接拼接历史成功报告。
- 阻塞：无需新增用户选择；所有外部协议仍诚实标记UNVERIFIED，不将当前局部checked当作WB-03完整验收。
