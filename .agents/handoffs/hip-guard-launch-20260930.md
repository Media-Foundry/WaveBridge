# 交接：守卫候选 launch 与复制效果

- 日期/分支/基线：2026-09-30，wb03-source-ast，9190e20；开始工作树干净。
- 用户约定：中文、持续推进，直接commit并周期push，不创建PR。
- 驱动：softmax_launch_native新增固定hip-guard输入profile，旧profile不变；
  threads-object模式独立报告所选block槽copy效果，不靠初始化门槛签发它。
- 核心改动：record_copy_check局部效果对default visibility采用与
  constructor_effects相同窄规则，完整保留属性；未知/缺证据仍拒绝。
- 实际验证与工件：见experiments/hip-guard-launch-20260930.md；01失败记录
  保留，02新报告中launch和局部copy effects checked，输入/实现未变。
- 真实新发现：所选copy来源就是上一轮对象；对象有11个switch case各两次
  引用（block和grid helper），不是唯一使用。不能替换为简化单copy程序。
- 未解除：object_boundary unknown、parameter_target unknown、closure旧
  初始化selection_domain_missing。局部copy父级checked不能覆盖子项unknown。
- 未运行：本轮不重新编译原HIP，不链接/执行CPU程序或GPU，不测性能。
- 提交/推送：主agent完成最终全测后直接提交同步；原始大工件留在artifacts。
- 下一项：让结构闭合不依赖外部手填初始化值域，并在组合层消费fresh守卫
  来源；核实真实配置callee的形参目标支持边界，然后建立完整switch路径的
  对象历史与grid/block其它实参的效果。不要直接把32/4/1当成launch值。
- 阻塞项：无外部阻塞。上述是待实现的语义检查，不是要求用户补权限。
