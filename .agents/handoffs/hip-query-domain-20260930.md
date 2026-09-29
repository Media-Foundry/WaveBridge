# 交接：外部查询数值域与条件算术

- 日期/分支/基线：2026-09-30，wb03-source-ast，1f2a7c4；初始工作树干净。
- 用户约定：中文，持续推进，验收后直接commit/push当前分支，不开PR。
- 实现：integer_selection.check_minimum_quotient_domain独立算术；
  check_query_power_quotient可选精确query-value-domain/v1协议。
  协议必须明确是external assumption；不从历史测量推断域。
- 验证：1359项全测122.075秒通过无跳过，/tmp/wb-query-domain-check.log；
  Clang23/17各16项19.868/20.399秒；数学3项含4位穷举对照；demo/diff通过。
  Sol只读复核无阻断。
- 原HIP证据：artifacts/wb-hip-query-domain-20260930-01/report.json，SHA256
  f619a82b41b9515944fa695049ee46f3c0d7199158ebf432faaabfe6ed23e4a0。
  未验证[32,32]假设下得到商[4,4]；不是新API数值域证明。
- 范围：conditional安全true，旧实际安全/domain verified/launch/deploy false。
  非零原义务保留；域失败顶层unknown/rejected仍可保留符号relation。
  消费数值需同时核status与division_safe_under_domain_assumption。
- 没执行：原TU重编译、程序/GPU、性能测量。没有改变历史基线结论。
- 提交/推送：主agent验收后直接提交同步；大型原AST/artifacts仍本地。
- 下一项：为同次查询值建立源码运行时守卫或独立目标协议绑定；
  不把hip-query-domain-hypothesis-20260930.json当能力证书。
  若插入guard，需重新采集候选AST并检查guard→minimum保持，不改写旧输入证据。
