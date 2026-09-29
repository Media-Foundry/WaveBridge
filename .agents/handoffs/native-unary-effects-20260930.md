# 交接：一元 native 条件效果

- 日期、分支、基线：2026-09-30，`wb03-source-ast`，`8d607ce`。
- 用户目标及约定：持续推进源码门控；中文回复，直接commit/push，不建PR。
- 完成：builtin callsite checker显式一元模式，从fresh外层结构、实参和
  参数链组合fresh leaf效果协议。零参旧路保留。column_loops的显式
  call-effects入口可传播选项，默认不放行新模式；协议/模式绑定哈希。
- 真实回归：小型Clang源码循环正例条件recovered；实参递增、induction写入
  负例unknown。直接builtin、using策略、错协议和结构/效果分离有断言。
- 验证：全量1258项105.238秒通过，无跳过；make demo/diff通过。native
  SDK23专项20项1.107秒，AOCC17 native+driver28项1.066秒，补充断言后的
  SDK23定向28项1.168秒。全量使用匹配SDK23/AOCC17混合配置，不称全量SDK23。
  日志`/tmp/wb-native-effect-{check,demo,aocc,targeted}.log`。
- 复核：GPT-5.6 Sol只读未发现阻断；已补direct与策略边界断言，文档明确
  driver协议映射非完整inventory、结构checked不升级效果unknown。
- 实际HIP重放：见`experiments/hip-native-effect-evidence-20260930.md`；
  是未验证leaf假设下的敏感性检查，不是设备库效果认证。
  5个互异语法call均条件checked，进程退出0/observed，src/driver哈希前后及
  结束后一致；协议映射与结果ID集合一致。报告SHA256
  `a8af8a027126343d9221d593efdd2a1e709b1ba1588d89ee129fcf21fa9f617b`。
  后补断言的AOCC17定向28项再次1.169秒通过，aocc-final日志保留。
- 未执行：GPU、生产TU重编译、性能测试、远端CI核验。
- 保证边界：条件无写只针对精确call；前提必须覆盖实际到达的所有参数值。
  初始化、存活、边界等前提保留；不证明builtin值、FP环境、完整循环或部署。
- 提交/推送：本轮随实现/测试/状态提交，以实际Git记录为准。
- 下一步：将选定数学调用的显式效果前提接入真实HIP循环work检查并定位剩余
  拒绝原因；另需验证实际lowering语义，不用本轮assumption替代实际库证据。
- 运行状态：本轮全部进程已终止，无遗留任务或外部授权阻塞。
