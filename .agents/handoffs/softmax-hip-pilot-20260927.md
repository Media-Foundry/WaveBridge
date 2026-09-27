# 交接

- 日期、分支、基线：2026-09-27，`wb03-source-ast`，`14510bf`。
- 约定：中文，直接commit/push当前分支，无PR、不合并master；用户已授权本机W7900。
- 完成：独立手工HIP compat/harness、冻结18case参考与协议、可重放编译/设备/
  数值runner、精确名称metadata复用入口、结果索引及失败记录说明。
- 最终设备验证：10号工件18/18通过；API/probe/目标实例编译wave32一致，
  block=(32,4,1)、grid=ceil(rows/8)，实际HIP库dladdr及哈希已记录。
- 最终报告：`artifacts/wb-softmax-hip-pilot-20260927-10/report.json`，SHA256
  `f53b5800c54e8ef5ec459b7734e3c4edf0a6064e8e519357881926e28b78cab2`。
  输入、生成文件、二进制前后哈希一致；74555会话已正常结束，不再重跑。
- CPU：完整1205项（93.310秒，无跳过）及最终8项专项通过，demo/diff通过；
  2481会话已结束。日志08/check-final.log，首轮测试失败06/check.log原样保留。
- 技能/复核：run-experiment用于本机预检与小任务执行；GPT-5.6 Sol提供独立
  数值协议/reference和测试，复核发现的padding NaN过度保证已修为位模式
  sentinel保持，不证明无写入。详细时序见experiments实录。
- 局限：手工编译width32、default-stream和HIP API shim，不是PyTorch运行库、
  自动适配或旧CUDA AST的继承验证；未测性能、native64或通用生产TU。
- 提交状态：本交接随验收实现提交，push以终端结果为准。
- 下一项：对最终生成HIP头与harness重新采集完整AST/依赖，连接同一实际
  执行工件与源码关系；不能复制CUDA sm80旧ID或把数值通过当静态检查通过。
