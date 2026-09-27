# 交接：受限 using 引用身份

- 日期、分支、基线：2026-09-27，`wb03-source-ast`，`b1ae14a`。
- 目标与约定：持续推进可信源码恢复与检查；中文回复，直接commit/push，无PR。
- 实现：UsingShadowIndex受限匹配唯一普通FunctionDecl与引用展开，原AST不改。
  scalar_forwarding/scalar_call_effects opt-in消费；策略与版本绑定成功报告哈希。
  不全局去重、不扩展builtin语义。规则见docs/decisions/0004。
- 实际重放：四份真实HIP重复声明身份查询checked；两个math builtin仍结构
  unknown。命令/哈希与边界见`experiments/hip-using-shadow-evidence-20260927.md`。
- 实际验收命令：
  `WB_USING_SHADOW_COMPILER=/home/husrcf/anaconda3/lib/python3.12/site-packages/_rocm_sdk_core/lib/llvm/bin/clang++ WB_NATIVE_CAPTURE_PLUGIN=artifacts/wb-native-template-OqD1PQ/libwavebridge_capture_plugin.so WB_NATIVE_CAPTURE_COMPILER=/opt/AMD/aocc-compiler-5.1.0/bin/clang++ make check`。
  1238项通过，97.463秒，无跳过；make demo与diff检查通过。
  `/tmp/wb-using-shadow-check.log`、`/tmp/wb-using-shadow-demo.log`。
- 复核：GPT-5.6 Sol未发现P1；已补策略哈希绑定与普通后代重复负例。
- 未执行：GPU、性能实验、远端CI核验、全量SDK Clang23测试。既有Clang18 CI
  可能skip展开表示专项，不应宣称远端已执行新版真实回归。
- 保证范围：可信Clang表示上的身份解析与普通scalar参数链条件组合；不是
  native数学builtin效果、完整循环、浮点等价或部署保证。
- 未提交/推送：此交接随同代码、测试和状态提交；最终以Git实际记录为准。
- 下一步：同一native输入上的一元float builtin身份/实参结构；保持副作用
  实参负例和外部效果协议边界，不直接套用huge_valf/nanf规则。
- 阻塞：本轮任务均已完成，无运行任务需重启，无外部授权阻塞。
