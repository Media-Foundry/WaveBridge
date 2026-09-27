# 交接：HIP exp/log 的实际结构边界

- 日期、分支、基线：2026-09-27，`wb03-source-ast`，`15155fe`。
- 目标与约定：持续推进真实源码适配门控；中文回复，直接commit/push，无PR。
- 完成：扩展既有`experiments/softmax_call_audit.py`支持固定native输入；
  诊断层可显式遍历完全相同的重复声明，保留次数。非相同声明只逐次保存，
  不任选一份放行。生产checker和AST均未修改。
- 新证据：exp/log在UsingShadowDecl中重复表示；expf/logf两份仅loc.file
  显式出现与否不同。native识别builtin_expf/logf，旧checker结构不支持。
  完整命令、精确ID、哈希与局限见`experiments/hip-math-call-evidence-20260927.md`。
- 实际测试：
  `WB_NATIVE_CAPTURE_PLUGIN=artifacts/wb-native-template-OqD1PQ/libwavebridge_capture_plugin.so WB_NATIVE_CAPTURE_COMPILER=/opt/AMD/aocc-compiler-5.1.0/bin/clang++ make check`。
  最终1223项通过，96.221秒，无跳过；`make demo`与`git diff --check`通过。
  日志`/tmp/wb-hip-math-final-check.log`、`/tmp/wb-hip-math-demo.log`。
- 未执行：GPU、性能实验、远端CI核验、全量Clang23回归。
- 保证范围：诊断清单不证明完整路径、动态可达性、调用效果或整核正确性。
  没有新增效果协议，source/deploy仍false。
- 提交/推送：本交接随同代码、测试和状态提交，以Git实际记录为准。
- 下一项：真实Clang最小using引用与冲突负例，明确可接受的重复表示；
  然后一元float builtin结构与实参效果。禁止全局忽略重复ID或任意位置差异。
- 阻塞：本次诊断和测试均已终止，无活跃任务需要重启；不存在外部授权阻塞。
