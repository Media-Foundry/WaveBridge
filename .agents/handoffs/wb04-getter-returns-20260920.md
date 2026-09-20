# Getter 返回域独立检查

- 日期/基线：2026-09-20，wb03-source-ast，6dc3c68；初始工作区干净。
- 用户约定：中文、直接commit、验收后push当前分支、不创建PR。
- 完成：`verification/getter_returns.py`从原始单TU AST重建唯一声明调用链，
  检查零参/单return/static起点、外部叶ID/实参，以及整个显式区间的整数值保持。
  不导入analysis或transforms，不接受生成器自报的路径或成功状态。
- 外部协议：getter-leaf-domain/v1，精确ID、非负常量实参、Clang类型对象及
  lower/upper；ABI显式传入。checked只证明受限getter的条件返回值保持。
- 子代理：GPT-5.6 Sol实现合成与真实Clang测试并只读审查主实现；主代理增加
  预算、真实函数递归、畸形children、非有限输入、非static及实参转换失值负例。
- 验证：`make check` 331项通过；`git diff --check`；真实CPU检查命令
  `PYTHONPATH=src python3 artifacts/wb04-getter-returns-fVQljU/check_final.py`。
- 输入：沿用 `artifacts/wb03-initializer-value-02/{report,ast}.json`，启动前核验
  源报告SHA与AST字节SHA；不重新编译或执行GPU。实际传入起点ID来自已有value_link，
  但checker从完整AST独立检查其函数体，而非相信旧报告的trace。
- 显式假设：unsigned long64/unsigned int32/int32，外部leaf(0)返回[0,255]。
  这不是实际thread/launch/轴域已获证明；仅用来检验转换链的条件性质。
- 结果：safe checked，返回unsigned int域[0,255]；人为反例域[0,2^32] rejected，
  unsigned long→unsigned int转换反例4294967296，不将此域描述为真实GPU线程数。
- 最终report：`artifacts/wb04-getter-returns-fVQljU/report-final.json`，SHA256
  `8b4b7bd13f8a766872de21f8a5c1cf5b118dbfd316bdc30bea8c5c23fa7e243a`。
  报告绑定规范化root/起点/协议/ABI hash和实际实现hash；运行前后实现hash一致。
  初轮check.py/report.json在最终收紧前产生，保留但不作为最终版本证据。
- 边界：完整函数签名类型一致性依赖faithful Clang AST；不解析重声明链，不
  验证外部函数实现、receiver纯度、外部域真实性或初始化表达式。部署始终false。
- 未执行：GPU数值、性能或自动候选生成。工件在本地ignored目录，不等于云端复现包。
- 下一项：将已检查getter返回域与value_link的外层转换、显式local-id轴语义及
  实际block配置逐项关联；不通过名字猜坐标，不把不同AST ID/旧报告混合使用。
- 本轮改动仅实现、测试、协议、状态与交接，验收后commit并push。
