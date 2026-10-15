# Fresh配置到普通内层入口交接

- 日期/分支/基线：2026-10-15恢复，wb03-source-ast，9d97bac。
- 用户目标：持续推进真实源码适配；中文回复，直接commit和定期push，不建PR。
- 实现：block_configuration.check_guarded_coordinate_to_fixed_nested_entry从
  本次fresh配置派生leaf域，再fresh检查固定嵌套入口。不接受旧域/通过状态。
  核对root/native envelope、owner、局部/两层循环、ABI、预算与协议哈希。
- 真实结果：artifacts/wb-hip-config-fixed-20261003-01/report.json条件checked，
  fresh_configuration_composed=true，入口域[0,31]；工件哈希见实录。
- 恢复事项：旧会话及/tmp日志缺失，未据其猜测全量测试结果；本轮重新跑全量
  make check和Clang17专项，日志保存在上述artifacts目录，不再只放/tmp。
- 边界：API/provenance/noalias/调用效果/正常完成等仍为前提。线程参与、
  硬件限制、列覆盖、source/deploy未建立；没有新GPU执行。
- 验收：1403项全测469.787秒，Clang17专项16项210.340秒，无跳过通过；
  demo/diff通过。结果与命令见experiments/hip-config-fixed-20261003.md。
- 下一项：实际列访问覆盖，而非新增独立布局模型。真实inner内element_index
  声明0x7769241ac278，initializer加法0x7769241ac3c8，引用local_idx
  0x7769241ab3f0、it 0x7769241ac110、WARP_SIZE 0x7769241aa6d8。
  batch_element_count声明0x7769241abf78，条件表达式0x7769241ac0c8，
  依赖outer i 0x7769241abe10、local_batches 0x7769241ab178和
  element_count参数0x7769241d55f0。这些是本轮完整AST定位，不是覆盖检查结果。
- 现有guarded_stores依赖break分区，不可为迎合它改写原kernel；index_partition
  仅支持/和%，也不是上述加乘索引的直接入口。需复用适用的表达式/递推检查。
- 当前改动准备提交推送；具体提交身份和干净状态以git记录为准。无外部阻塞。
