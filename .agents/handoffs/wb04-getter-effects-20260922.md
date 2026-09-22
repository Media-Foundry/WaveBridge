# 交接：Getter 条件无写检查

- 日期、分支和基线：2026-09-22，wb03-source-ast，a62535d。
- 用户目标：继续推进源码门控；中文回复，直接 commit/push，不建 PR。
- 已完成：Sol 子代理实现 getter_returns.check_no_memory_write 和协议单测；主代理
  审查并补充真实 Clang 正负例、严格布尔前提与值域 fresh 重检回归。
- 实际验证：make check（503 项通过）、make demo、git diff --check。
- 未执行：GPU、完整 vLLM TU 的新 checker 检查、整核或候选适配验收。
- 保证：受限 wrapper 在显式叶无写/正常返回假设及既有值域/ABI 前提下条件无写。
  外部引用 unverified，source_program_checked/deployable 均 false；不接 body 放行。
- 原始工件：artifacts/wb03-coordinate-api-bzKGaT/，默认忽略，不随 Git 推送。
  report.json SHA256：52e2daaa337cee29e80a947146ea86ad905cc6c891e4fc8fd62a6facc01e6f6d。
- 同 TU 诊断：固定完整 AST SHA256
  5b612a12a1955a3db65467d16fb69c9df7501f29d828403cae0a38b8995afa4f；
  getter 0x248ca3b0，leaf 0x248cb458，leaf 类型 int () noexcept。
  projection 只用于诊断，不作为完整 TU 输入签发检查。
- 编译诊断：`/opt/AMD/aocc-compiler-5.1.0/bin/clang-17 -std=c++17 --cuda-device-only --cuda-gpu-arch=sm_80 -nocudainc -nocudalib -S -emit-llvm -O0 artifacts/wb03-coordinate-api-bzKGaT/builtin_probe.cu -o artifacts/wb03-coordinate-api-bzKGaT/builtin_probe.ll`。
  单 builtin 调用 lowering 为 llvm.nvvm.read.ptx.sreg.ctaid.x，声明 memory(none)。
  这不是执行证据，也不自动把 probe 与任何同名 AST 叶绑定。
- probe source SHA256：767a5dc3587a2d0343d2fab091338a883488fce9d5107ef4bc31cb17a7108957。
- probe IR SHA256：b20d53a43185e4ee5ff196742a9a2266e1e88a68fa931f138531660d0a70c0c1。
- compiler SHA256：0aafa5b0712f974db5bbdd93a849b0b1e094bbb6314b8163278a22a90ce766b8。
- 提交安排：本交接与实现一起提交并推送；远端新提交 CI 未核验。
- 下一项：建立完整 TU 有界声明检查、实际坐标域与 receiver 求值的组合；保持当前
  vLLM unknown，不能把新增条件 API 当成独立谱系验收成功。
- 阻塞项：无新增用户输入要求；上述语义义务尚未实现。
