# WB-03 起点初始化证据交接

- 基线 `d977c33`，分支 `wb03-source-ast`；中文、直接commit，无PR。
- 新增initializer_evidence：精确VarDecl定位、完整初始化AST、调用清单及无参getter trace；const/volatile和多调用边界显式保留。
- source.py把每个唯一循环起点接到初始化证据，报告绑定分析实现哈希。特殊call kinds不被漏计。
- 真实HIP两个循环共同起点含getter→OCKL local id调用，但PseudoObjectExpr值等价/receiver/转换/外部语义均未证明。
- `make check` 130项通过（8项真实Clang），无新GPU数值或性能运行。
- 下一步：建立受支持属性读取的结果选择规则及外部接口协议，才可赋予线程索引语义；并开始恢复shuffle实际路由，不能把当前调用证据当完整跨lane恢复。
