# 交接：Host配置到device local_idx初始化域

- 日期/分支/基线：2026-09-30，wb03-source-ast，d171a9b，开始工作树干净。
- 用户目标：持续推进完整适配门控；中文回复，直接commit/push，不创建PR。
- 完成：block_configuration新增check_guarded_local_coordinate，fresh配置字段
  →显式API轴协议→派生local-ID域→同kernel直接局部initializer/getter/转换。
  不把真实二维block压成一维，不输入数值上下界。旧RMSNorm入口保持不变。
- 测试：最终make check 1390项336.992秒无跳过；Clang17最终专项8项74.126秒；
  Clang23首轮8项62.384秒，后加负例在最终全测执行通过。demo/diff通过，
  Sol只读复核无阻断。日志/tmp/wb-block-coordinate-{tests,clang17,check,demo}.log。
- 真实工件：artifacts/wb-hip-block-coordinate-20260930-01/report.json，SHA256
  244c413bf898bbf70d52b9f60339001a841db0e50be2a86b776b663cca053741。
  三轴32/4/1、线程乘积128，派生leaf[0,31]，实际local_idx初始化域[0,31]。
  22copy、配置与initializer同root，转换checked。命令及所有hash见实验实录。
- 未执行：新HIP/GPU运行、性能或跨波宽实验。完整Clang23 capture兼容性未补齐。
- 边界：轴及leaf API语义、运行时配置对应仍是明确外部假设；未验证硬件限制、
  local_idx后续历史、线程参与、源/目标等价或部署。不是WB-03完整研究验收。
- 提交：与代码/协议/实验文档直接提交并push当前分支，不合并master。
- 下一步：把派生初始化域保持到真实列访问/循环入口，再连接列覆盖与子组关系。
  先复用既有initializer/history与循环检查；不要重新手填该坐标域或按函数名
  填写固定关系。API真实性与实际设备条件继续作为单独门槛处理。
- 阻塞：无本轮实现阻塞；上述运行时与语义义务未解除。
