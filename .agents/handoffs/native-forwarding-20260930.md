# 交接：wrapper 到 native builtin 参数转发

- 日期、分支、基线：2026-09-30，`wb03-source-ast`，`ea08716`。
- 目标及约定：持续推进真实源码检查门控；中文回复，直接commit/push，无PR。
- 完成：scalar_forwarding新增inspect_builtin_structure，先fresh native leaf
  检查再重走受限wrapper链。终端call和当前wrapper形参精确绑定，必须实际
  消费指定leaf；旧外部leaf入口继续使用原逻辑。
- 实际重放：真实HIP exp→expf→builtin与log→logf→builtin各两层参数转发
  checked。最终02工件、命令和hash见
  `experiments/hip-native-forwarding-evidence-20260930.md`。首版01完整保留。
- 复核修订：GPT-5.6 Sol未发现P1；按P2为native child增加独立schema、
  terminal_mode及envelope/call/policy哈希，父报告显式汇总假设/局限。
- 实际验证：最终make check 1249项通过，98.512秒、无跳过；make demo和
  diff通过。新unary/using专项使用SDK23，既有native专项使用AOCC17插件。
  环境设置与上一份unary-builtin-20260930交接相同；最终日志
  `/tmp/wb-native-forwarding-final-check.log`、`/tmp/wb-native-forwarding-demo.log`。
  17项专项0.250秒通过，11项AOCC native专项0.148秒通过。
- 未执行：GPU、性能实验、全量SDK23、远端CI核验。
- 保证边界：只检查函数定义内部参数结构，不检查外层实参、builtin效果、
  值/正常返回、完整循环或部署；outer_argument_effects_checked始终false。
- 提交/推送：随本交接提交代码、测试与状态，以实际Git记录为准。
- 下一步：精确外层callee绑定与实参求值，再与fresh native参数链组合；
  不把语法来源call清单直接当作外层调用正确性证据。
- 阻塞：本轮进程已终止，无需要重启的任务，无外部授权阻塞。
