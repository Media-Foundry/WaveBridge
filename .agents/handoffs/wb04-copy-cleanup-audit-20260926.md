# 复制结构与析构效果边界

- 日期2026-09-26，分支wb03-source-ast，实现基线454f574。中文；直接commit/push，不开PR。
- 审计时完整TU会话95200仍运行；随后已退出0，三个独立结构点与fresh v3组合均checked，77个实现哈希一致，源码冻结解除。产物目录artifacts/wb-independent-effects-r0Eik8，终态见wb04-independent-copy-effects-20260926.md。
- 454f574远端CI 36233180736已completed/success；此状态不替代本地完整TU终态。

## 主代理实际CPU反例

目录artifacts/wb-copy-cleanup-audit-nODmIv，包含cleanup.cpp、check.py、CPU二进制和report.json。
运行：PYTHONPATH=src python3 artifacts/wb-copy-cleanup-audit-nODmIv/check.py，退出0。
脚本使用Clang17真实AST、明确int/unsigned32 ABI、fresh inspect_effects，并编译执行同一源码。

带单个unsigned字段的record有隐式trivial copy ctor，但用户析构递增全局计数。
局部source按值传给consume后，函数内计数为1；source作用域结束后为2。
实际stdout：after_parameter=1 after_source=2。
结构入口checked；surrounding_cleanup_and_destructor_effects仍not_established。
record.definitionData.dtor明确nonTrivial=true/userDeclared=true。
parameter_target为unknown（真实非平凡析构引入临时包装）；本例不声称绕过该目标绑定门控。

源码SHA256：d207a1d0ff01a72adfff480654d4c719f77ed146abf690d4f2caae3ad2a3e27a。
报告SHA256：f1da4f6390390cff95cb1a9b495386d2f44cabc58172c4dc2d1659b3197c17ee。

这是当前checker正确保留边界的有限CPU见证，不是源对象被修改的反例，更不是GPU结果。
未改变src或tests，不增加全仓测试数。docs/status.md和本交接随重放终态一起提交。

## 下一步

只读Sol审查建议：从fresh结构入口分别建立目标完整对象/精确按值参数绑定，以及
正面trivial destructor和必要native cleanup检查。不可以只检查没有DestructorDecl。
即使这些局部义务成功，也不证明不透明调用、非标准栈探测、并发或完整历史保持。
会话95200终态及77个实现哈希已核验，可开始下一项实现；现有alive协议仍保留。
