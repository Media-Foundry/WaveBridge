# 交接：一元条件效果连接次数边界

- 日期、分支、基线：2026-09-30，`wb03-source-ast`，`6da8587`。
- 用户目标与约定：继续真实源码门控；中文回复，直接commit/push，无PR。
- 完成：现有check_iteration_bounds显式传播一元/using开关至fresh work；
  工作保持与区间计算仍分别检查，父hash/假设继承。driver新增互斥
  --iteration-bounds模式，guard输入使用完整signed-int32区间，未猜测launch。
- 验证：1268项CPU回归104.284秒通过，无跳过，demo/diff通过；SDK23 native
  25项3.726秒、AOCC17 native+driver30项3.813秒、driver5项0.005秒通过。
  全量使用匹配SDK23/AOCC17混合配置，不称全量SDK23。
  日志`/tmp/wb-unary-bounds-{check,demo,targeted,aocc,driver}.log`。
- 复核：GPT-5.6 Sol只读无阻断；full int32只作外部ABI范围，不代表动态覆盖
  或初始化事实。fresh声明选点报告不是输入域证明，最终checker再次检查。
- 实际重放：命令/固定输入/结果见
  `experiments/hip-unary-bounds-evidence-20260930.md`。
  默认unknown，启用条件checked，外层工作区次数界[0,2]，header count2。
  进程退出0/observed；输入/src/driver前后及结束后hash一致，父子假设与
  策略hash复核一致。报告SHA256
  `05f67b33b9acf236dc2503acadf80d48a97ad07d78ea832b2edaffbc2eab0c18`。
- 未执行：GPU、生产TU重新编译、性能测试、远端CI核验。
- 边界：次数界不等于完整域，nested/work-body算术、输出覆盖、FP值、库效果
  与部署未建立。读取有效性、存活、源有效性、不别名等前提保留。
- 下一步：对实际nested/工作区整数索引和初始化前提逐项连接，而不是把
  iteration_bounds_established误当成full_iteration_domain_established。
- 提交/运行：本轮进程全部结束，无遗留任务；随本轮提交并推送，以Git为准。
