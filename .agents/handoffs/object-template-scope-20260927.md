# 交接

- 日期/分支/基线：2026-09-27，wb03-source-ast，e225c10；中文回复、直接提交推送。
- 完成：constructor_argument_effects、object_initialization、object_use_closure 的
  独立结构入口支持精确 instantiated_function_id opt-in；默认与旧条件 API 不变。
  三层 fresh 绑定唯一具体实体/函数体/实参，输入摘要包含选择 ID。
- GPT-5.6 Sol 完成两个新增测试文件和只读复核，无阻断。未放宽共享 AST ID、
  替换表达式或动态直接读取的支持边界。
- 验证：全量 1153 项/92.558 秒、native 启用无跳过；最终增加一方法后专项
  6 项/0.287 秒通过，demo/diff 通过。没有把这写成最终1154项全量复跑。
- 真实重放：artifacts/wb-object-template-check-Xt4l2i/replay.json，SHA256
  12c97b3e46973677127a6a8db278a788b8a84553d10e9533c01aead013d03911。
  原session67356正常结束；inputs_unchanged及结束后的实现/driver hash核对通过。
  launch checked，threads对象 unknown；绑定实例0x30a41828，构造来源仍缺
  selection_domain。必须读取threads_object_check，不能只读顶层launch状态。
- 未验证：GPU、复制时配置值、host可达性、完整线程参与及整核语义。
- 下一步：从实际warp_size API及其更新、warps_per_block算式建立构造点值来源
  和历史；不把手工32域塞入constructor作为恢复证据。实例门槛已推进，构造值
  和历史门槛未解除。无需重复上一项长时间pointer-history重放。
