# 交接：guarded work 消费一元条件效果

- 日期、分支、基线：2026-09-30，`wb03-source-ast`，`b163b0e`。
- 用户目标与约定：持续推进真实源码门控；中文回复，直接commit/push，无PR。
- 完成：loop_exit_guards的work入口显式传播一元/using选项，默认False；
  子调用前提纳入父，策略绑定hash。其它work/guard/prefix/nested检查保留。
  新实验驱动从3份固定SHA工件只取协议字典，不取旧成功结论。
- 实际重放：原HIP外层输出循环默认unknown/call_effect_not_checked；启用
  模式在显式未验证前提下checked。log、nan两个call与一个nested循环重新
  检查，无unused协议、无static prune。实录和命令见
  `experiments/hip-unary-work-evidence-20260930.md`；报告SHA256
  `895bf85d521d3401cfa7f025fb672d256ec9d2ec218dc1269c9621303efa59e7`。
- 验证：最终1263项CPU测试106.134秒通过，无跳过；make demo/diff通过。
  SDK23 native23项2.760秒，AOCC17 native+driver25项2.559秒通过。
  混合编译器验收，不称全量SDK23。日志`/tmp/wb-unary-work-final-check.log`
  及实录所列定向日志。GPT-5.6 Sol只读复核无阻断，建议的回归已补齐。
- 未执行：GPU、生产TU重新编译、性能测试、远端CI核验。
- 范围：只建立条件guarded work保护依赖存储；leaf效果、完整迭代域、FP值、
  源程序及部署未建立。实验import辅助脚本未单独前后hash，不称完整依赖闭包。
- 提交/推送：随本轮代码/测试/状态提交，实际Git记录为准。
- 下一步：4处exp属于无break计算循环，应检查其真实剩余递推/工作义务，
  不能套用guarded入口；同时设备库实际效果仍缺独立lowering/语义证据。
- 阻塞及进程：本轮进程全部终止，无遗留任务，无外部授权阻塞。
