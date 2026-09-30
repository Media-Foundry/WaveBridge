# 交接：条件构造字段保持到复制读取

- 日期/分支/基线：2026-09-30，wb03-source-ast，f73f727；开始工作树干净。
- 用户目标：持续推进源码恢复与门控，中文回复；直接commit并定期push，不创建PR。
- 完成：field_snapshot新增fresh组合入口，不读旧通过报告；核对完整引用/字段
  双射/非发布/顺序/cleanup，明确restricted provenance模型。新增真实Clang
  正负例、架构/协议说明与决策0005，未放宽旧复制类型支持子集。
- 验证：冻结make check 1382项259.326秒无跳过；Clang17专项28项147.621秒，
  顶层hash补充后对应测试再跑1项6.331秒通过；demo/diff通过，Sol只读复核。
  日志/tmp/wb-copy-model-check-final.log、/tmp/wb-copy-model-clang17.log、
  /tmp/wb-copy-model-clang17-final-binding.log。首次fixture拒绝及01报告保留。
- 工件：artifacts/wb-hip-copy-model-20260930-02/report.json，SHA256
  1365905a0938b1749389d8d871637b0cbcae430a063cf6bbae405baaa5f6450c。
  frozen native输入不变；完整22copy，字段32/4/1，父子实例hash一致。
- 未执行：新GPU/HIP程序、性能实验、跨波宽部署；没有增加此前Clang23完整
  capture兼容性的保证。
- 范围：仅模型内选定copy若执行的字段保持；旧栈/跨activation retained
  pointers等被显式外部假设排除，不是自动证明不存在。实际provenance、
  launch/source/deploy仍false，完整WB-03与研究创新性未验收。
- 提交：本交接与代码一起直接提交并推送当前分支；不合并master。
- 下一步：将条件copy字段结果与同次选定launch的精确block槽绑定，继续区分
  API/ABI及实际运行时对象前提。不能把模型成功直接改成配置或GPU部署通过。
- 阻塞：无实现阻塞；真实对象来源/平台契约仍是未解除的研究与部署义务。
