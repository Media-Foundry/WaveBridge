# 条件调用进入循环保持性交接

- 日期/分支/基线：2026-09-27，wb03-source-ast，8328e5e。
- 约定：中文；验收后直接commit/push，不创建PR。
- 实现：默认recover不变，新增独立native+protocol入口；fresh完整调用检查
  才可跳过其子树，嵌套内外保护均接入，其它节点照常检查。
- 防混用：新父/子schema和外部保持性标记；未知父报告保留partial证据但不升级；
  未消费协议使父unknown。协议不是成功报告或已验证语义。
- 实际结果：原有softmax native重采collected；新driver同AST默认1 recovered/
  7unknown，显式未验证假设下4recovered/4unknown，父unknown；无GPU/新谱系。
  固定哈希、实际命令和边界见experiments/column-builtin-evidence-20260927.md。
- 验收：1010项/67.080秒/native插件/无跳过；demo/diff通过。
  日志 artifacts/wb-column-builtins-twz82w/。
- 子代理：GPT-5.6 Sol真实Clang回归及复核，额外协议拒绝已加入。
- 未验证：外部builtin效果、输入域、FP/参与/整核/设备语义、远端CI。
- 下一步：从新native报告定位剩余exp/log、collective调用和控制流；不要把
  4/8局部条件递推写成生产kernel已经验证。检查哈希/扫描成本后再扩支持。
- 提交：本轮验收后提交推送。
