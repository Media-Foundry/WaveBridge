# 模板 bool 与循环 hint 包装的副作用边界

基线 a7ef9d6，分支 wb03-source-ast。本轮不生成 GPU 工件，不做新 holdout。

## 新支持及可信边界

- bool SubstNonTypeTemplateParmExpr 只接受 typed prvalue 的真实 bool literal。
  可有一个完整、非 pack、没有额外 child 的 bool 参数声明；不检查模板实例化
  正确性，不据此删除 if 或条件表达式分支。其它替换保持 unknown。
- body 中 AttributedStmt 只接受 1～8 个无表达式 child 的 LoopHintAttr 加
  一个 ForStmt，随后按同一深度/递推/body 门槛检查原循环。实际 AST 中的
  attr `inner:[{}]` 是被支持的空槽；非空表达式、其它 attribute 拒绝。

Clang 将这类 pragma 描述为循环优化提示，参见
[官方语言扩展文档](https://clang.llvm.org/docs/LanguageExtensions.html#extensions-for-loop-hint-optimizations)。
这里不从不含 option 的 JSON 猜测具体 unroll/vectorize 模式或额外前提，
不证明优化器或机器码语义。检查对象只是原始源码循环的条件关系。
顶层 ForStmt 的平面发现不检查其外层 pragma metadata；本轮门槛仅作用于
body 包装路径，不得宣传为完整 pragma 验证。

## 验收设计

新增 5 项 fixture 回归和 6 项真实 Clang 测试，由 GPT-5.6 Sol 独立编写源码
测试并复核。覆盖两种 bool 值、metadata 有/无版本、空/错误/带副作用子树、
未选分支中的写入/调用、pragma 包装内写入/call/break/三层循环、hint 参数
表达式。CPU 只执行合法正例，输出 `1 4 5 3`。
另显式回归局部 nested 证据存在但父级后续调用失败的情况：父级 unknown、
body_preserves_induction/bound 未建立、checked/deployable false 均不得升级。
带 count 参数的 hint 必须放在外层 body 中，测试才确实经过包装门槛；测试
显式区分编译器是否给出表达式 child。即使某版本省略 child，接受也仅为
effect-shape 观察，不代表已恢复 count 值或具体 hint 选项。

## 固定真实 AST 回放

```bash
PYTHONPATH=src python3 -m experiments.softmax_constant_followup \
  --ast artifacts/wb-pytorch-softmax-KhwXBa/attempt-02/ast.json \
  --previous-report artifacts/wb-pytorch-softmax-KhwXBa/attempt-02/report.json \
  --output-dir artifacts/wb-column-wrappers-ywAkXI/replay
```

report.json SHA256：
`3c01b98b7727f042a5fdb279cffe2e37a370bde6ab893752e57cecd6fb5763e9`。
输入、实现和 driver 前后哈希稳定。8 个循环中，第 3 个（从 0 开始、上游
123–138 行的 max 阶段内层循环）恢复为 start=0、bound=4、step=1，词法
深度为 1。其 body 两条条件分支都检查，未利用 is_masked=false 删除分支。

剩余 7 个循环为 6 个 call_in_body、1 个 unsupported_control_flow_in_body；
父级整体仍 unknown。第 2 个外层循环保留一项已经完成的局部 nested 证据
（iterations=4、final_induction=4），但随后遇到调用而失败；该局部证据不能
替代父级 body_preserves 标志，更不能单独放行外层循环。归约仍无候选，12 个调用
未解析。局部递推不证明 max 运算正确、数据归属、collective 或整个 kernel。
这不是独立目标上的接受率，也不是新冻结/盲测；原首次评估报告不修改。

工件与日志：artifacts/wb-column-wrappers-ywAkXI/。
最终 make check（check-final.log）在匹配 native capture 插件启用下运行
959 项测试，66.834 秒，全部通过且无跳过；定向 11 项通过，Clang17/SDK23
新增源码各 6 项通过，demo 与 diff 检查通过。
没有新前端采集、GPU、目标生成、数值或性能实验，未核验远端 CI。
下一步应对剩余直接调用逐例
绑定实现并建立明确效果；不得按 exp/infinity 等名字硬编码“无写/正常返回”。
