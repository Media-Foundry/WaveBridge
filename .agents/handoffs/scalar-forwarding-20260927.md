# 单标量参数转发交接

- 日期/分支/基线：2026-09-27，wb03-source-ast，daa3321。
- 约定：中文，验收后直接commit/push，不创建PR。
- 实现：scalar_forwarding.inspect_structure，从完整AST精确检查单float参数
  按值转发链到无body leaf；不赋予数学函数效果/数值语义。
- 实际回放：新native softmax的首个剩余call blocker，exp→expf→__nv_expf
  两层结构checked，参数声明逐层对应；driver和固定哈希见
  experiments/scalar-forwarding-evidence-20260927.md。
- 测试：GPT-5.6 Sol新增5项真实Clang，重命名正例、替代/修改参数、算术/转换、
  额外写/递归/错leaf/指针/引用拒绝，以及32/33层和AST预算边界。
- 完整验收：1015项/66.554秒/匹配native插件/无跳过，demo/diff通过；
  日志 artifacts/wb-scalar-forwarding-PFKZhi/check.log 与demo.log。
- 未执行：GPU、前端重采、远端CI；没有新的循环/整核接受。
- 边界：caller实参表达式效果、external leaf语义和正常返回未建立。剩余另
  两个循环为动态break，不可忽略其实际退出语义。
- 下一步：独立检查实际标量实参的求值效果，并以精确leaf协议连接有限转发链，
  再考虑数学调用进入循环；不直接按exp/log名称放行。
- 提交状态：本轮验收后提交推送。
