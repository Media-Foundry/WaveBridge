# 交接：launch参数绑定与构造参数

- 日期、分支、基线：2026-09-20，`wb03-source-ast`，`9df010b`。
- 用户约定：中文、直接commit，无PR，未推送。
- 实现：launch_facts为每个site保存按唯一kernel定义和实参位置绑定的形参ID；constructor_arguments解析带精确构造ID的functional cast，记录参数位置/默认来源/转换与转换前常量，不赋予字段或实际配置语义。
- 验证：`make check`196项通过，`git diff --check`通过。普通Clang fixture的CXXTemporaryObjectExpr缺精确constructor ID，返回unknown；正向证据来自真实HIP AST和结构回归。
- HIP命令：沿用wb03-discovery中的完整源码入口命令，输出目录换为 `artifacts/wb03-source-launch-arguments-01`。AST及全部实现hash核对一致。
- 结果：4个kernel实参与形参绑定；block转换前参数256/1/1，首项声明ID等于归约helper BLOCK；grid首项symbolic，后两项默认1来自AST，不是人工补值。
- 未证明：constructor字段映射、整数转换后值、运行时grid/block、host输入和kernel的数值对应。未执行新的GPU或生成适配候选。
- 下一步：沿精确constructor声明核对字段初始化，并在显式目标ABI/输入域下检查参数转换；仍需坐标外部语义与完整源/目标检查，G1共同案例差异尚未验证。
