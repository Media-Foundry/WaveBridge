# 循环体条件表达式与 softmax 剩余边界

基线 e474a8b，分支 wb03-source-ast。沿用已固定、已分析过的真实 PyTorch
softmax AST；不构成新的 holdout、生产 TU 支持或 GPU 结果。

## 变更及负例

普通 ConditionalOperator 要求恰好三个非空 AST 子节点，并对条件及两个分支
完整执行原有副作用检查；不求条件值、不删除所谓死分支。条件左值写入仍由
存储目标检查拒绝。GNU BinaryConditionalOperator、缺失分支保持 unknown。
这不是整核等价或终止性检查，无别名、源有效性等前提不变。

新增 3 项结构 fixture 测试及 3 项真实 Clang 测试（11 个源码函数），覆盖
正例、三个位置的 induction 写入、bound 写入、条件左值和两个分支的调用。
literal false/true 的未选分支含调用也拒绝。GPT-5.6 Sol 独立编写源码测试
并只读复核；Clang17 与 SDK Clang23 的新增源码测试各 3 项通过。

## 实际回放

```bash
PYTHONPATH=src python3 -m experiments.softmax_constant_followup \
  --ast artifacts/wb-pytorch-softmax-KhwXBa/attempt-02/ast.json \
  --previous-report artifacts/wb-pytorch-softmax-KhwXBa/attempt-02/report.json \
  --output-dir artifacts/wb-column-condition-tzD8H8/replay
```

输入、实现及 driver 前后哈希一致。最终 report.json SHA256：
`469d3301f469f21b16a7cddee293a0fba9c546d0c06e47328b84595b096ae527`。
四项常量仍为 128/32/4/2，8 个循环头均观察到，8 个循环仍 unknown。
归约候选与未解析调用没有改善；不计有效接受率提升。

逐循环按选定实例的源码顺序定位拒绝 range，而非在整个 TU 按相同范围猜选：

| 循环序号（从 0 开始） | 首拒绝 | 对应 AST 节点 |
| --- | --- | --- |
| 0 | nested_loop_in_body | ForStmt |
| 1 | unsupported_storage_target | ArraySubscriptExpr（二维写入） |
| 2、4 | unsupported_body_effect | AttributedStmt（循环 pragma 包装） |
| 3、5、7 | unsupported_body_effect | SubstNonTypeTemplateParmExpr（bool） |
| 6 | unsupported_control_flow_in_body | BreakStmt |

部分 template substitution 与子 literal 共享 range，记录两者匹配而不宣称
range 是唯一节点身份。报告保留原始 AST，表格只是人工定位说明。
与上一轮相比，普通条件表达式不再阻断，暴露出后续嵌套循环和 pragma 包装。

验收日志位于 artifacts/wb-column-condition-tzD8H8/{check,demo,clang23}.log。
make check 在匹配 native capture 插件启用下运行 932 项测试，67.194 秒，
全部通过且无跳过；make demo 和 git diff --check 通过。
没有新 GPU 执行、没有新 softmax 前端采集、没有解除外部调用与控制流义务。
下一步应先确定嵌套循环需要的保持与终止义务；不能直接把 loop/pragma 名字
加入白名单，也不能因模板 bool 为 false 就未经检查删除另一条路径。
