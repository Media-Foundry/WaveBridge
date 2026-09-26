# builtin wrapper 交接

- 日期/分支/基线：2026-09-27，wb03-source-ast，ac7bfc1。
- 约定：中文；验收后直接commit/push当前分支，不创建PR。
- 实现：builtin_calls.check_wrapper_no_memory_write 检查整个单返回函数体和
  精确callee链，最多32层；末端fresh检查builtin结构和外部效果协议。
- 实际回放：CUDA合成探针4个入口conditional checked（含两条numeric_limits
  两层链）；带参数写入函数unknown。协议仍是演示用外部假设，没有自动验证。
  哈希和范围见experiments/builtin-wrapper-evidence-20260927.md。
- 测试：GPT-5.6 Sol新增真实Clang测试及独立复核；零参global write、逗号、
  递归/unknown、instance/virtual、错leaf、32/33层边界；另3项fixture回归。
- 完整验收：最终1000项/66.335秒/匹配native插件/无跳过，demo/diff通过；
  日志 artifacts/wb-builtin-wrappers-3uFzg5/check-final.log 与demo.log。
- 未执行：GPU、生产softmax重采、远端CI核验。无独立谱系或整核接受结论。
- 局限：没有返回值、FP环境或纯度保证，外部caller receiver/args排除；不能
  以partial wrapper_declaration_ids升级unknown父报告。
- 下一项：实际调用点的完整callee/receiver/参数求值检查，再考虑以明确效果
  协议接入循环分析；不直接按函数名开放body调用。
- 提交状态：本轮验收后提交推送。
