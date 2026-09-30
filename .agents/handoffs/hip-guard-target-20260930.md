# 交接：配置按值形参目标

- 日期/分支/基线：2026-09-30，wb03-source-ast，72564e3；起始工作树干净。
- 用户目标与约定：持续推进真实源码适配链，中文，直接commit和周期push，无PR。
- 改动：record_copy_check._parameter_target允许明确default visibility的callee，
  其它身份/类型/位置/参数数量限制不变；完整属性观察与链接未建立状态明确记录。
- 真实结果：同一冻结候选block槽copy绑定参数0x2caec560（位置1），局部效果、
  按值目标、对象边界结构checked。对象历史/初始化值域闭合仍unknown。
- 验证与工件：experiments/hip-guard-target-20260930.md记录命令、hash与最终测试。
  真实Clang32项专项分别使用17/23；Sol只读复核无阻断。
- 未执行：本轮没有重新编译原HIP，没有链接或执行程序/GPU，没有性能实验。
- 保证边界：同一AST中的语法按值目标及受限record边界，不证明动态源存活、
  对象值保持、其它实参/cleanup/callee效果、配置API、链接或部署。
- 下一项：解除对象结构闭合对手填初始化selection_domains的依赖，保留旧接口，
  新组合必须fresh连接guarded constructor而非接受旧成功报告。然后核对真实
  switch全部22个引用及grid侧效果，不能退化成只有一个copy的替代程序。
- 提交/推送：最终验收后由主agent同步当前分支；大原始工件留本地artifacts。
- 阻塞：无外部阻塞，剩余为实现与语义验证工作。
