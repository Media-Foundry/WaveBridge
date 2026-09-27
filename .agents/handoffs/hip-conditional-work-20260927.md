# 交接：HIP 条件输出循环重放

- 日期、分支与基线：2026-09-27，`wb03-source-ast`，`86c8435`。
- 用户目标：持续推进可信源码关系与门控；中文回复，直接commit/push，不创建PR。
- 完成：既有builtin-effects driver增加独立HIP输入绑定和可选guarded-work对照；
  新增4项明确标注mock的编排测试。生产checker和native输入未修改。
- 实际验证：重放命令、报告SHA和完整范围见
  `experiments/hip-conditional-work-evidence-20260927.md`。
  两个原始嵌套输出循环无假设unknown、有精确leaf假设条件checked；通用恢复
  仍4/8 unknown，不能用局部结果代替整体恢复。
- 全量验证命令：
  `WB_NATIVE_CAPTURE_PLUGIN=artifacts/wb-native-template-OqD1PQ/libwavebridge_capture_plugin.so WB_NATIVE_CAPTURE_COMPILER=/opt/AMD/aocc-compiler-5.1.0/bin/clang++ make check`。
  1219项通过，93.242秒，无跳过；`make demo`通过。
  日志：`/tmp/wb-hip-conditional-check.log`、`/tmp/wb-hip-conditional-demo.log`。
- 未执行：GPU、性能测量、远端CI核验、全量Clang23回归。
- 未解除：外部leaf效果/正常返回假设、完整迭代域、浮点等价、整核与部署。
  构建输入完整闭包亦未建立，实验导入辅助模块不属于driver自哈希。
- 提交/推送：本交接随同driver、测试和状态记录提交；以Git实际记录为准。
- 下一步：在同一HIP输入上明确剩余exp调用的语义证据和支持边界；不得把
  合成lowering观察直接升级为生产调用效果证明，也不得盲增无依据假设。
- 阻塞：本次条件重放已完成，无需重启或追加GPU作业。
