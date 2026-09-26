# 交接：默认实参与shuffle剩余义务

- 日期、分支、基线：2026-09-27，wb03-source-ast，edc0e51；开始工作树干净。
- 用户约定：中文，直接commit/推送当前分支，无PR、不合并master。
- 完成：array_call_effects字面量defaultarg可选检查；replay选项与原始
  shuffle链摘录；5项真实Clang测试；编译专用shuffle_leaf.cu探针；证据/状态。
- 验证：1105项全过，75.392秒，新native插件启用、无跳过；demo/diff通过。
  GPT-5.6 Sol测试/复核。探针+ptx60生成LLVM IR成功；缺PTX feature的首次
  失败及重放日志保留。不把失败记成缺工具或无支持语义。
- 工件：artifacts/wb-array-defaults-Fpxw7d/replay.json，SHA256
  419bfbc1553852cc931e25903684fda8a0fdaa029b2ca36694892fba6bce44ee，inputs_unchanged=true。
- 结果：默认参数0x30d89140 / defaultarg0x30dce258 / literal0x309f4c28
  的unsigned int 4294967295求值条件checked；7处写入保持；pending仅剩
  CallExpr0x30dce1d0。父级unknown，尚未接入历史保持。
- 下一层：callee0x30d89288 → __shfl_xor_sync0x2e2c7bf8 → builtin调用
  0x2e2c8318/callee0x2e2c7d78 (__nvvm_shfl_sync_bfly_f32，native ID1726)。
  leaf第四参数0x2e2c82d0为((warpSize-width)<<8)|31，const全局0x2dc920b0。
  不能当作全参数直接转发或省略控制表达式效果。
- 关键边界：本机LLVM声明和实际探针IR均为inaccessiblemem readwrite、
  convergent/nocallback，而非no memory write。应设计可访问程序存储保持
  的明确leaf前提/检查，不谎称intrinsic完全无内存效果。probe sm80/+ptx60
  不认证完整production编译/设备/参与/数值。所有哈希/命令见实验实录。
- 未执行：GPU、生产AST重采、远端CI；原生工件继续使用OqD1PQ，不混旧ID。
- 下一项：fresh检查两层wrapper、叶实参和builtin身份，再显式连接可访问
  存储效果协议及正常有效执行前提。不能仅因名字或IR属性就直接解除整个调用。
- 提交范围：本轮源码/测试/driver/probe/文档；大型工件不入git。
