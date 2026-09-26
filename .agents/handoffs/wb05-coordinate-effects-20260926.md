# 坐标 property 副作用门控

- 日期/分支/基线：2026-09-26，wb03-source-ast，7ce6503；初始干净。
- 用户约定：中文、直接 commit/push 工作分支，不 PR、不合并 master。
- 实现：双侧入口 v4 要求 coordinate_effects.row/start，fresh 检查本次 row/thread
  已选 property 求值，无新的外部成功报告 API。缺协议、错接或不支持即 unknown。
- 边界：仅精确 property 求值，不含声明写入。外层转换仍由旧 initializer/domain
  路径约束；external leaf no-write/normal-return、receiver readiness/extension
  semantics 均为未验证外部假设，不是 SDK 纯度或整个 initializer 证明。
- 验证：匹配 native 插件环境 make check：813 tests，64.634 秒，OK；make demo
  与 git diff --check 通过。5 项新增真实 Clang 测试未 mock property checker，
  但外围 row/thread/domain 是显式测试输入；另有 1 项 mock 顶层门控。
- Sol 子代理：实现新增真实 Clang 测试、随后只读审查父级集成，未发现阻塞问题。
- 本地工件：artifacts/wb-coordinate-effects-DuMwKl/，含 tests.log、demo.log、
  run.py 与 source/target-conditional-protocol.json。协议是明确声明的条件测试
  假设，不是独立验证证据；ID 从固定旧报告选取，实际 checker 全部 fresh 重跑。
- 真实固定 AST 重放由主代理等待并追加结果；本轮不重新编译 HIP、不执行 GPU。
- 下一步：明确点态跨执行的 input/count/坐标对应与 FP 环境协议，配合现有
  局部模板、偏移和求值检查；不可仅靠位置/区间相同宣布叶值相等。外部假设
  应独立核实或留在条件保证中，不能伪装为已自动推导。
- 提交与推送：全部验收完成后主代理统一执行，不提交忽略工件。
- 最终真实 v4 重放：350.332 秒，退出 0；两侧 row/start 四项均 checked，
  外部前提仍未验证、叶值未建立，父 evidence、实现哈希稳定。report.json SHA256
  11b6443164f424142a8ebd3027849696b7a1e9cfc160577b32ea73cfb8496942。
- 新条件协议 SHA256：source 7cd20460b90499d31a51784a5ada5ba71979c5c01a8fdacfef10f8e4cab97e99；
  target 0a28a2846bed385bc0cbdb1a789979fa4114b5e7930236576edc43cb800c003f。
