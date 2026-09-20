# 条件共享容量检查

- 日期2026-09-20；分支wb03-source-ast，基线b2a25f4；中文、直接commit。
  用户本轮新增定期推送授权，验收后推送当前工作分支，不创建PR或合并master。
- GPT-5.6 Sol实现 `verification/shared_bytes.py`及专用测试；主代理审查、要求
  加强畸形children与预算前hash深树处理，并实现capacity组合及CLI。
- 表达式checker只支持非负字面量、括号、值保持整数转换、sizeof(type)与乘法；
  每个节点类型由显式ABI描述，sizeof由显式表提供。溢出、负值、窄化、未知符号、
  调用、预算耗尽或畸形AST均unknown，不能按32或float名字猜字节数。
- `verification/shared_capacity.py`按精确kernel ID连接site和链，在受限块模型
  下计算block_threads/width个partial槽位。静态shared用声明extent，动态shared
  用launch第三配置实参；不拿动态字节补不足的静态数组。容量不足rejected。
- `shared_capacity_check.py`提供新CLI；重复JSON字段/非有限常量拒绝，输出不可
  覆盖，绑定源报告、显式ABI与实现哈希。缺launch或未解析launch不能整体checked。
- 示例 `examples/abi/storage-conditional.json`是假设，不是设备探测证据。
- 测试306项通过，涵盖合法128字节、刚好32、短31/0、static不足/extern不明、
  ID/ABI不一致、动态变量、转换溢出、非法sizeof、畸形child、深树预算、空launch、
  未解析launch、缺失/重复launch ID、存储报告一致性和不可覆盖输出。
  Sol复审提出的门控缺口已修复，顶层报告也显式携带前提。
  测试使用模型/AST fixture，不替代硬件结果。

实际命令：

```
PYTHONPATH=src python -m wavebridge.shared_capacity_check artifacts/wb03-shared-binding-02/report.json --abi examples/abi/storage-conditional.json --output artifacts/wb03-shared-binding-02/capacity-check-reviewed.json
```

结果为checked，required_elements=8，required_bytes=32，available_bytes=128。
最终报告SHA256：`c1f747374735060904ed6f5bd6df72e2335b88a6dc95dcacdf1ee4cf7e7320fc`。
capacity-check.json及capacity-check-final.json为复审硬化前记录，保留不覆盖。

边界：source AST绑定未重新验证；假定结构恢复忠实、实际block及坐标匹配、ABI
匹配、第三配置实参确为dynamic shared bytes、单数组起于偏移0且无其它动态分配。
alias/参与者/源有效性仍未证明。这里checked不表示运行时内存安全或整核等价。
本轮无GPU执行、无数值容差修改、无性能结论。
下一步把实际launch block字段与已恢复block_threads建立独立一致性检查，减少
当前“实际block符合模型”这一外部前提；不要直接把本报告作为部署门控通过。
