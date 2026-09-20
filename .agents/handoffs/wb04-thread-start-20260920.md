# 同一 AST 的条件线程起点组合

- 日期/基线：2026-09-20，wb03-source-ast，39d7432；初始工作区干净。
- 用户约定：中文、直接commit、阶段性push、不创建PR。
- 完成：`verification/initializer_domain.py`核对value-link/getter报告的callee、
  ABI、类型和整个区间的逐级初始化转换。它消费可信前端/真实checker证据，不声称
  重新验证pseudo-object恢复；checked只表示条件域值保持。
- `thread_start_check.py`为组合API，独立重新运行同root的源码恢复，再调用block、
  getter、initializer三项checker。root hash/kernel/launch绑定，配置位置明确grid0/
  block1；外部坐标协议绑定leaf ID/axis0/返回类型。域由block.x导出而非手填。
- Sol实现初始化checker/测试并审查组合；发现block旧报告预设坐标结论，已从
  block_configuration删除该不必要前提。另补配置位置exact int及checked block
  维度合法/一维/模型匹配门控；Sol复审确认无残留循环。
- 验证：`make check` 342项通过；单独11项组合/初始化测试通过；`git diff --check`。
  组合单测明确mock前端/配置，仅测编排门控；真实HIP检查使用原始完整AST重新恢复。
- 实际命令：
  `PYTHONPATH=src python3 artifacts/wb04-thread-start-psY2gK/check_final.py`
- 输入：`artifacts/wb03-initializer-value-02/{report,ast}.json`；运行前核验其字节hash。
  显式外部协议保存在同目录binding-final.json，绑定规范化root hash
  `91b528c4ed158ed3d817740a3b5cc4580ab2a28d6436320c3fd1a517a7d1ea57`，
  kernel `0x2dc5f250`、launch `0x2dc9f5b8`、local-id leaf `0x2d2b62f8`。
  FieldDecl x/y/z和配置位置均为明确外部API假设，不算自动发现。
- 最终结果：block/getter/initializer均checked，起点`0x2dc5f5c0`区间[0,255]。
  最终report SHA256：`c6f044bfac184772be794bc04c0e7dfa78526cfe10525a71ecb50a38d593802b`。
  报告为 `artifacts/wb04-thread-start-psY2gK/report-final.json`，全部实现hash与
  运行前后匹配。初轮report.json含旧循环前提，仅保留历史，不作为最终结论依据。
- 保证边界：只条件性连接选定launch下列起点与local x。可信前端、Clang不变量、
  有效源码/receiver、ABI、外部leaf/axis语义、真实运行配置仍为前提。不是所有
  线程参与、归约helper内其它坐标、数值/内存安全或源目标等价保证。
  source_program_checked/deployable始终false。无GPU执行，无候选代码生成。
- 下一项：将同样的精确坐标/转换关联应用于block helper的lane/group分解，再把
  已建立的列起点与实际列数域/覆盖检查连接，继续解除通信关系的具体前提。
- 本地artifacts忽略，不等于云端复现包；本轮实现、测试、协议、状态及交接验收后
  commit并push当前分支。没有PR或master合并。
