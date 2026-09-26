# 局部计算入口关系连接

- 日期/分支/基线：2026-09-26，wb03-source-ast，ed99b30；开始时干净。
- 用户约定：中文、直接 commit 和推送当前分支，不创建 PR、不合并 master。
- 实现：device_evidence.compare_rmsnorm_routes 升级 v3，私有连接仅消费本次
  fresh side/local 子结果；绑定 snapshot root/kernel/int_bits、prefix 的同一
  local recovery、自动声明及 input/start/bound/accumulator ID。
- 双侧签名：参数角色/类型/位置、整数 ABI、row/start/count 区间、坐标 API
  语义/axis/返回类型和 source offset 的整数关系/结果类型。不同签名或缺失
  连接保持 unknown，不继承 route evidence 成功。两侧 host guard 模式分别记录。
- 范围：不是外部成功报告验证 API；不建立实际运行实参、input 内存内容或
  浮点叶值对应，不证明前提集合相同。两侧所有嵌套前提仍必须满足，deployable false。
- 验证：匹配 native 插件下 make check：807 项，65.987 秒，OK；make demo、
  git diff --check 通过。新增 4 个私有连接 fixture 方法和 1 个 mock 编排方法，
  不称为真实源码分析。Sol 只读检查未发现阻塞问题。
- 工件：artifacts/wb-entry-binding-7zmON3/ 保存日志与重放脚本；固定真实源/目标
  AST 重放由主代理等待验收后登记。不重新编译 HIP 或运行 GPU。
- 下一步：把已有 check_property_no_memory_write fresh 接入两侧精确 row/start
  initializer 求值路径，显式绑定 leaf effect/receiver 假设，不能将外部无写前提
  说成自动纯度证明。随后还须提供点态跨执行 input/count/坐标关系协议，不能
  仅凭参数位置和区间相同推断值相等。保持 pointer/alias/FP/参与义务。
- 提交与推送：真实重放验收后统一执行，不提交忽略的大型本地工件。
- 最终真实重放：319.728 秒，退出 0，v3 evidence，入口签名相同，运行实参、
  指针内容及叶值仍 not_established；实现哈希前后稳定。报告位置：
  artifacts/wb-local-structure-hfn1Di/report-entry-binding.json，SHA256
  231b52ad9b0627676c92498e69c2dafbab183773aed1aa3d72d190a17dbde2c5。
  实际复用了旧 run.py，stdout v2 文案不代表 JSON schema；已用 jq -e 单独
  核对 v3 与入口签名成功。本轮目录内脚本已改 v3 文案并加相应断言。
