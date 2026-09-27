# 0004：受限 using 引用展开身份，不做全局 AST 去重

- 状态：采纳，2026-09-27。
- 背景：实际SDK Clang23在UsingShadowDecl下再次输出FunctionDecl及函数体。
  exp/log副本完全相同，expf/logf仅根声明loc.file显式出现与否不同。单纯要求
  AST树中每个ID只出现一次会挡住这些输入；按ID任选一份又会掩盖真实冲突。

## 决策

引入共享`UsingShadowIndex`，目前由scalar_forwarding和scalar_call_effects
两个入口显式opt-in消费，默认仍严格单次出现。输入AST不修改，不过滤节点后
重新声称检查了原始程序，也不改变其它checker的身份策略。

每个查询身份必须有且仅有一份非shadow展开中的普通节点。其它副本必须位于
唯一、implicit、单FunctionDecl child的UsingShadowDecl内，target精确绑定
该函数的id/kind/name/type；整份函数声明与唯一普通定义比较一致。
仅根声明loc.file的单边省略可接受：另一侧需有非空文件名及有效offset/col/
tokLen，剩余loc字段和整个声明（含所有子节点）完全一致。两个显式文件名
冲突、范围/宏位置/后代位置变化均不忽略。该例外是可信Clang表示下的缺省
诊断位置容忍，不证明源码文件位置完整恢复或不同文件中的代码等价。

验证后返回原普通节点，后代身份仍需唯一普通出现，不能仅因父声明匹配就
消除后代在其它普通位置的重复。嵌套引用展开不支持。逐份保存两侧哈希、
引用target和采用的匹配策略，模式与策略版本纳入成功报告input_sha256。

## 保证边界

依赖同一忠实Clang AST的前提。这是表示身份，不是函数无副作用、值等价、
动态调用或整核证明。调用与实参仍fresh通过原语义检查，效果协议依旧是
未认证外部假设。新的一元builtin结构尚未因本决策而获得支持。

## 验证

真实Clang23 using函数链与副作用负例、显式标注的AST冲突fixture，以及
真实HIP四份重复声明重放。旧Clang若不输出展开副本，专项明确跳过；普通
fixture仍在无Clang环境运行。不得把跳过写成新版真实前端回归通过。
