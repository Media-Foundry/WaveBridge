# 交接

- 日期、分支、基线：2026-09-27，wb03-source-ast，aec70c5。
- 目标：将条件浮点界推进到实际工具链证据；中文回复，直接commit/push。
- 完成：读取官方RDNA3 ISA §16.8/印刷页276的V_RSQ_F32精度与denorm说明；
  核对当前SDK wrapper/OCML及既有gfx1100 IR/汇编路径。没有把HIP有限测试表
  当成全域精度保证。experiments/rsqrt-isa-evidence-20260927.md记录链接/哈希。
- 实现：experiments/rsqrt_domain_audit.py fresh检查全部1023个列长、两种
  累计模式和两种显式宽度，4092配置；区间约[9.999998807907139e-7,
  4.001004530074643]，不依赖rsqrt误差假设，条件排除非正规数路径。
- 证明：PROOF_PACKAGE.md新增ISA适用域和两种明确ULP解释到rho=2^-22的
  保守转换；proof-writer指导明确假设，GPT-5.6 Sol复核未见阻断问题。
- 验证：新增3项CPU回归；匹配native插件下make check共869项通过，无跳过，
  68.464秒；make demo、git diff --check通过。全域审计另行完整执行。
- 工件：artifacts/wb-rsqrt-domain-yOlR83/，报告SHA256
  8da39ee1f0a9a8238946e710a2d0143ada021b9987f37d1b645172f9637a2ea9。
- 未执行：新编译、GPU、实际runtime ISA契约验证、数值容限验收。
- 边界：条件模型域/文档前提，不是源程序/机器码对应；rsqrt契约实际适用、
  其他算术律、冻结reference舍入误差未闭合，deployable=false。
- 提交状态：本交接随实现提交并推送当前分支；不创建PR、不合并master。
- 下一步：连接实际编译后缀与ISA前提，或冻结reference的舍入误差；不能把
  文档或区间checked单独升级为GPU候选放行。
