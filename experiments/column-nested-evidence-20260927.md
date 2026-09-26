# 一层嵌套递推与外层保持性

基线 86698b4，分支 wb03-source-ast。新增的是有明确拒绝边界的源码分析，
不是 softmax 整核接受、真实 GPU 适配或新的独立谱系验收。

## 条件保证

内层 fresh 恢复必须成功，且只有非负 literal 起点、非负 const 声明上界和
正步长。次数 k=max(0,ceil((b-s)/d))，末值 s+k*d 必须在外部 signed ABI
范围内。保留完整内层恢复报告，checked/deployable 仍 false。

内层对自身 induction 的保持不能替代对外层的保持：其初始化、条件、增量、
body 全部针对外层 protected 声明重新检查。源有效、无别名、正常 body 执行
仍是条件，不证明内存安全。call/break/while/深层嵌套及动态内层域保持 unknown。

只读复核曾发现平面循环清单可把中间层重新当顶层的问题；修复后清单带
lexical_loop_depth，仅 depth=0 启用嵌套组合，后代不重置嵌套预算。
第三层函数整体和中间层均 unknown；最深叶循环仍可有单独条件递推诊断，
不表示整个嵌套被接受。原 unsigned coordinate 及 property-body 路径未扩展。

## 测试

新增 4 项 fixture 测试：含 256 组小域枚举次数/末值对照、最后增量溢出、
外层 induction/bound/start 保持检查及未知边界。原空 nested ForStmt 负例
仍拒绝，原因由笼统 nested_loop_in_body 更新为 unsupported_for_header_layout。

GPT-5.6 Sol 独立新增 4 项真实 Clang 测试并复核，含同名不同声明 ID 正例、
9 类负例、三层词法深度回归及合法 CPU oracle。CPU 仅执行两个正例，输出
`1 4 3`；8bit 溢出是显式外部 ABI 下的模型测试，不称实际 Clang int 为8bit。
Clang17 和 SDK Clang23 各 4 项通过。早期 targeted.log 有新增测试字段尚未
同步造成的失败，保留；以字段和深度断言修正后的 targeted-final.log 为准。

## 固定真实 AST 开发回放

```bash
PYTHONPATH=src python3 -m experiments.softmax_constant_followup \
  --ast artifacts/wb-pytorch-softmax-KhwXBa/attempt-02/ast.json \
  --previous-report artifacts/wb-pytorch-softmax-KhwXBa/attempt-02/report.json \
  --output-dir artifacts/wb-column-nested-3GsYSn/replay-final
```

最终报告 SHA256：
`2cbf67767dc2b7769825425a9d59e4f0ec06efb232e198929aabb93bb41098be`。
输入、实现、driver 前后绑定稳定；depth 为 `[0,1,0,1,0,1,0,1]`。
8 个循环仍全部 unknown，nested_loops 成功条目仍为 0：首拒绝现在为
5 个 unsupported_body_effect、2 个 unsupported_storage_target、1 个
unsupported_control_flow_in_body。第一层循环不再直接因嵌套而拒绝，
但内层二维写入不受支持，父循环同样拒绝；没有放行部分成功证据。

早期 replay/ 是深度边界修复前工件；最终实现对应 replay-final/。
不重写首次冻结结果，不把开发反馈计为新 holdout；无新前端采集、GPU
执行或远端 CI 核验。日志位于 artifacts/wb-column-nested-3GsYSn/。
完整 make check 启用匹配 native capture 插件，940 项通过（68.373 秒，无
跳过）；最终列循环定向 70 项通过（4.522 秒），demo 与 diff 检查通过。

下一步可针对二维内建数组的存储根和索引副作用建立边界；不把任意复杂
左值递归剥离为变量，更不能因此放过引用或条件左值对 induction 的修改。
