# 显式输入关系下的抽象局部值组合

- 日期/分支/基线：2026-09-26，wb03-source-ast，d253657；初始干净。
- 用户约定：中文、直接 commit/push 当前分支，不创建 PR、不合并 master。
- 实现：新增 compare_rmsnorm_local_values，fresh 调用原 v5，原入口行为不变。
  paired-local-input-assumptions/v1 严格绑定两侧 root/protocol/kernel/launch/
  input/count；假设限定共同域内坐标、kernel entry 原始基址对应的同一不可变
  逻辑数组、有效完整局部执行与共同确定性顺序保持 typed-AST 解释。
  extra output_equal/accumulator_equal、缺字段、非严格 true、错绑定均 unknown。
- 保证：完整 typed seed/loop + ordered indices 经局部迭代归纳得到抽象
  loop-exit accumulator 对应。不是 C++ ==、bitwise IEEE 或机器码等价。
  实际 FP/输入关系均未验证，顶层 leaf/source/deploy 标记不升级；shared
  reduction/output 不在此条件结论中。共同 tuple 是域上的全称条件非实测配对。
- 验证：匹配 native 插件环境 make check：826 tests，62.344 秒，OK；make demo
  和 diff 检查通过。7 项 fixture/mock 测试，不称源码或 FP 证明。Sol 实现该
  测试文件并只读复核，未发现阻塞性范围问题。
- 工件：artifacts/wb-local-values-tIaIAb/，包括成对输入假设、两个 side effect
  协议、tests.log、demo.log、run.py。协议明确为未验证的抽象模型测试假设。
  绑定 ID 来自固定旧报告，公开入口全部 fresh 检查，不接收旧成功报告。
- 未执行：GPU、HIP 新编译、性能；冻结 tolerance 未改。
- 下一步：独立核实实际 FP 配置/输入协议与抽象模型的对应，再考虑 actual
  local leaf 结论；并回到独立代码谱系及完整适配验收，不把条件报告本身当
  WB-03/WB-05 全部完成或新颖性证据。
- 提交/推送：待固定真实 AST 重放终态后统一执行，不提交忽略大工件。
- 最终重放：350.976 秒退出 0，abstract local checked/conditional，父 evidence，
  actual_FP_semantics_verified/external_premises_verified 均 false，实际 leaf
  not_established，实现哈希稳定。report.json SHA256：
  75235646b54eb70efcb156fdf0ac889322983572c7c9949679dc33518e9b8602。
- paired-input-assumptions.json SHA256：
  414e42ee2def66b288f64bb0e42cb32bba9b1c9f5dc244598c8d25779ddb9586。
