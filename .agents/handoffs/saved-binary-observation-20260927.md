# 交接

- 日期、分支、基线：2026-09-27，wb03-source-ast，129e5d8。
- 目标：读取历史运行记录绑定binary中的真实设备代码，不以单独编译汇编替代。
- 实现：frontend.device_binary snapshot-first提取HIP AMDGPU对象并读取反汇编/
  notes，保存工具/命令/快照/产物摘要和完整原始输出。报告对象/重复键拒绝，
  哈希/提取/超时/缺输出/输入变化不能observed；observed只代表原始采集。
- 实际观察：历史3×777 W7900 baseline binary哈希17955611397d5bcc59cdb67c711059d600d6fa10515ec59cf9bbd970807c8442
  与报告双字段一致；device object5008字节，SHA256
  b5c8b8abaf3972c79b7008a50116d83d7a4d1a4ae53dbe8f76b5e397ac4c9977。
  gfx1100/wave32，kernel匹配；FMA@0x178c、rsq@0x19e8、outputmul@0x1a74。
- 工件：最终 artifacts/binary-observation-i0z96js_/，report SHA256
  614e9b19c21a7a032b4dd9331409b0612f5a60b4eda104329a27e6fa5a740cc9。
  初次手工提取和collector第一版产物也保留。初次LLVM在原binary旁新生成
  两个bundle已移入wb-saved-binary-X98JfN，原binary未改、未删除。
- 验证：7项新增mock测试；完整883项CPU测试64.987秒通过，native插件启用，
  无跳过；make demo/diff通过。真实LLVM采集两次成功、codeobject摘要一致。
  GPT-5.6 Sol独立只读复核路径和保证边界，非阻断报告格式建议已修复并回归。
- 未执行：编译、GPU、native64、数值容限新测试。
- 未建立：动态loader选择、kernel运行证明、所有动态参与/内存/指令误差律，
  源码→机器码等价和部署。metadata/FP/runtime/deploy标记保持false。
- 提交：随本轮直接commit/push当前分支，不创建PR或合并master。
- 下一步：使用实际code object接指令级语义或明确可信lowering前提；不要再
  把static opcode存在升级成运行与整核正确性，也不要停留在增加采集模块数量。
