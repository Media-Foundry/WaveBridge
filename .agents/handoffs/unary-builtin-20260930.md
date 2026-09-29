# 交接：native 一元 builtin 结构与参数读取

- 日期、分支、基线：2026-09-30，`wb03-source-ast`，`62c96dc`。
- 用户目标及约定：持续推进真实源码门控；中文回复、直接commit/push，无PR。
- 完成：builtin_calls新增显式unary/using选项，严格绑定expf/logf native身份
  与按值float形参读取；结构策略与版本绑定哈希。旧默认/wrapper入口不变。
  驱动新增--unary-float，保存真实HIP两处结构checked报告，不提供实际效果协议。
- 实际工件与命令：见`experiments/hip-unary-builtin-evidence-20260930.md`。
- 完整验收：`make check`运行1244项，95.525秒、无跳过；make demo/diff通过。
  日志`/tmp/wb-unary-builtin-check.log`、`/tmp/wb-unary-builtin-demo.log`。
  环境设置：WB_UNARY_BUILTIN_PLUGIN指向
  `artifacts/toolchains/clang23-native-8f497e0/libwavebridge_capture_plugin.so`；
  WB_UNARY_BUILTIN_COMPILER和WB_USING_SHADOW_COMPILER指向
  `/home/husrcf/anaconda3/lib/python3.12/site-packages/_rocm_sdk_core/lib/llvm/bin/clang++`；
  WB_NATIVE_CAPTURE_PLUGIN指向`artifacts/wb-native-template-OqD1PQ/libwavebridge_capture_plugin.so`；
  WB_NATIVE_CAPTURE_COMPILER为`/opt/AMD/aocc-compiler-5.1.0/bin/clang++`。
- 新6项专项：SDK23 0.089秒、AOCC17 0.094秒均通过。负例包含真实源副作用
  和明确标注的AST/native metadata mutations；不包装成GPU或数学语义保证。
- 未执行：GPU、性能、旧pilot复跑、远端CI核验、全量SDK23测试。
- 保证与剩余前提：仅leaf身份/实参结构。无写入组合仅在测试显式外部假设下
  演示；实际builtin效果、正常返回、FP语义、wrapper/loop及部署仍未建立。
- 提交/推送：本交接随同代码、测试与状态提交，以Git实际记录为准。
- 下一步：同AST参数转发wrapper到native leaf的独立结构连接，之后检查
  外层实参及效果协议，不能拿leaf成功报告替代完整调用链重建。
- 阻塞：所有本轮进程已正常终止，无需重启，没有外部授权阻塞。
