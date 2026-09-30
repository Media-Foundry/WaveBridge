# 交接：初始化数值无关的显式引用结构入口

- 日期/分支/基线：2026-09-30，wb03-source-ast，41034db；起始干净。
- 用户目标/约定：持续推进真实适配链，中文、直接commit和周期push，无PR。
- 实现：inspect_uses无数值域/旧报告输入，与旧inspect_structure共用私有core；
  新模式完全不调用初始化checker，独立root hash与inner/array_filler清单。
  旧接口保留旧前置门槛及遍历行为。新自动对象shape、copy/capture均fresh检查。
- 测试：未知参数初值+switch两分支真实fixture，旧入口unknown新结构checked；
  mock仅用于证明初始化函数未调用。写/alias/static/TLS/预算/隐藏引用负例。
- 验证：固定Clang17专项48项和全测1376项通过；具体时间、工件及hash见
  experiments/hip-independent-uses-20260930.md。首轮fixture未定义函数引起
  三个链接失败，已改参数输入并重跑，不掩盖初轮失败记录。
- Clang23兼容性：额外48项有29失败；基线旧模块46项也有同29失败，新两项通过。
  不得写成双编译器专项全通过，不将该兼容性缺口计作本轮已修。
- 边界：初始化值/effects/cleanup/completion均未建立，conditional_initialization
  为null；所有动态源存活、对象历史、API、配置值、部署保证均未建立。
- 未执行：未重新编译/运行HIP或GPU。专项包含既有小型CPU语义程序执行。
- 下一项：检查真实对象全部复制/清理结构报告，再fresh连接守卫构造来源与
  同一对象，从真实switch路径及grid/block实参效果建立历史；禁止手填域绕过。
- 真实重放已完成：22引用/22直接复制，逐次target/boundary均checked；source_order
  因source_order_do_outside_source_scope unknown，前序cleanup亦unknown。
  下轮先定位这条do/switch结构限制，不将父级结构checked当作历史证明。
- 提交/推送：主agent完成最终真实重放后同步当前分支；大工件保留artifacts。
- 阻塞：无外部阻塞；Clang23捕获兼容性是独立待处理技术缺口。
