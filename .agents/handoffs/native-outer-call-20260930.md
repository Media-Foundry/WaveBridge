# 交接：native 外层调用与实参求值

- 日期、分支与基线：2026-09-30，`wb03-source-ast`，`04a1e72`。
- 用户目标与约定：持续推进真实源码检查门控；中文回复，直接commit/push，不建PR。
- 完成文件：`scalar_call_effects.py`增加`inspect_native_call`，独立重新检查
  精确outer call、实参求值与native wrapper参数链。共享原直接callee绑定，
  旧条件外部leaf接口默认语义不变。驱动新增显式`--outer-calls`模式。
- 验收：1254项CPU测试通过（106.487秒，无跳过），make demo、diff通过。
  SDK23 native16项0.373秒；AOCC17 native16项0.363秒；后补父子哈希与模式
  断言的24项定向回归0.374秒通过。混合工具链配置同上轮交接；日志
  `/tmp/wb-native-outer-{check,demo,aocc,targeted}.log`。
- 复核：GPT-5.6 Sol只读检查未发现P1；按建议补充哈希断言，并明确语法
  路径选择器非穷尽，不能用空/全部checked结果宣布entry所有调用通过。
- 实际重放：命令、输入及最终结果见
  `experiments/hip-native-outer-evidence-20260930.md`。
  4处exp、1处log语法call均checked；进程退出0，observed。输入/src/driver
  前后及结束后哈希一致，父子输入哈希一致。报告SHA256
  `b9b982380d0eda950fb3c5dfe7d5256d72f0e4c08c3c90471b5e83333d582a95`。
- 未执行：新GPU作业、性能测试、生产TU重编译、远端CI核验、全量SDK23回归。
- 保证边界：只认证选定外层绑定、受限实参无显式写和参数结构。
  callee/whole-call无写、builtin值及正常返回、浮点等价、完整循环与部署
  未建立；存活/初始化/索引有效性仍为前提。指针下标未纳入支持。
- 提交/推送：本轮随代码与状态提交，实际状态以Git记录为准。
- 下一项：明确native math leaf的效果前提如何绑定与消费，再组合循环保护；
  不能因结构与实参已通过就默认SDK math调用无写或数值等价。
- 阻塞与运行进程：本轮重放和测试均结束，无遗留任务或外部授权阻塞。
