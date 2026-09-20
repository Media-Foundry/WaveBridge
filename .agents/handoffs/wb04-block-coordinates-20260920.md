# Helper 坐标与完整索引分解

- 日期/基线：2026-09-20，wb03-source-ast，a228b46；起始工作区干净。
- 用户约定：中文、直接commit、阶段性push、不创建PR。
- 完成：block_reduction新增index_initializers，保存group/lane的完整AST及
  外层转换；其原有coordinate/conversion未建立标记保持不变。
- 独立index_partition逐线程检查完整表达式恰为t//width或t%width；最多1024
  线程、128节点/32深度，每表达式恰含一个完整AST坐标锚点。显式ABI逐节点
  检查整数可表示性/转换值保持；错误算子/映射/窄化拒绝，不支持保持unknown。
- block_coordinate_check组合API从原AST重新发现已连接helper，并核对上游
  真实thread报告的root/ABI/binding hash、kernel/launch及width/block。
  分别连接两个坐标getter到相同leaf/axis协议并检查坐标转换，最后检查完整索引式。
  上游报告必须是真实checker输出；hash只绑定输入，不认证任意外部报告的真实性。
- 协作：GPT-5.6 Sol实现独立checker及回归，并只读审查组合层；主代理完善
  畸形输入门控、完整AST保存、组合与真实执行、等范围错误映射负例。审查未发现
  实质错误或循环前提。组合单测mock发现器，不能冒充源码恢复/硬件结果。
- 验证：`make check` 355项通过；`git diff --check`。
- 真实CPU命令：
  `PYTHONPATH=src python3 artifacts/wb04-block-coordinates-8Jv9Ru/check.py`
  从 `artifacts/wb03-initializer-value-02/ast.json` 重新执行thread和helper检查；
  原始AST/源报告字节hash先核验，全部src实现hash在运行前后一致。
- 输入外部协议：沿用 `artifacts/wb04-thread-start-psY2gK/binding-final.json`，
  显式int32/u32/ulong64 ABI来自storage-conditional示例；协议语义不算自动推断。
- 结果：helper `0x2dc5e208`，block256/width32；group逐点=t/32，范围0..7，
  lane逐点=t%32，范围0..31。两次不同AST调用均按相同外部API条件连接。
- 最终report：`artifacts/wb04-block-coordinates-8Jv9Ru/report.json`，SHA256
  `5daa4a036409d8ce4a825c563b16e7ce49e2a1751c7658e1bb3de163613af171`。
  同目录thread-report.json保存本轮重算上游证据。工件仅保存在ignored本地目录。
- 边界：source_program_checked/deployable=false；前端可信性、local-id语义在
  helper中成立、有效源码及实际launch配置仍为前提。未检查其它cast、writer
  谓词、参与收敛、同步/shared访问、shuffle/浮点等价。未GPU执行或生成候选。
- 下一项：把已建立的坐标关系与列数域/列覆盖、归约路由检查连接，并核对剩余
  predicate/index转换义务；再形成能检查真实候选的完整源码验收入口。
- 变更限定实现、回归、协议、状态与交接；验收后提交并推当前分支，无master合并。
