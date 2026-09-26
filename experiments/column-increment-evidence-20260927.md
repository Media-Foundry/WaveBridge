# 内建 ++ 递推及固定 softmax AST 开发回放

基线：059b629；分支：wb03-source-ast。新增的是受限语法支持，不是新的
独立谱系验收或 GPU 实验。GPT-5.6 Sol 编写真实 Clang 测试并只读复核实现。

## 实现范围

内建前置/后置 ++ 仅接受自动存储期 int induction、精确声明绑定、明确
类型/值类别及直接左值（允许同型括号）。保持原始 increment_ast，报告
step=1 和 builtin_increment 来源。循环体副作用检查、源有效性、外部
int_bits、溢出及别名前提不变；checked/deployable 不升级。

新增 2 项 fixture 测试和 5 项真实 Clang 测试；后者包括安全 CPU 对照。
引用/直接/逗号左值修改 induction 均 unknown。独立 stride-2 coverage
溢出测试只是数学模型边界，不冒充 ++ 源码到覆盖的组合证明。

## 开发回放

```bash
PYTHONPATH=src python3 -m experiments.softmax_constant_followup \
  --ast artifacts/wb-pytorch-softmax-KhwXBa/attempt-02/ast.json \
  --previous-report artifacts/wb-pytorch-softmax-KhwXBa/attempt-02/report.json \
  --output-dir artifacts/wb-column-increment-b6lr6e/replay-final
```

沿用已封存真实 AST，不重新运行前端；输入、实现、driver 前后哈希稳定。
最终报告 SHA256：
`64cd86927a6c86c0bf84b9644a2675ce5ed6924efa81e69b0202df88df511f53`。

四项常量仍为 128/32/4/2。8 个循环的 header_recurrence_observed 全部为
true，但循环整体仍全部 unknown：6 个 unsupported_body_effect，
1 个 unsupported_storage_target，1 个 unsupported_control_flow_in_body。
归约仍无候选，12 个调用未解析。没有整核接受，没有新 holdout 成功。
首次冻结结果不变；driver 内 previous 字段仍指首次冻结结果，而非上一轮
常量扩展后的报告。replay/ 为增加 induction 声明类型检查之前的中间运行，
replay-final/ 才与最终实现绑定。

完整验收日志：artifacts/wb-column-increment-b6lr6e/check.log；
demo.log；clang23.log。make check 实际 926 项通过，67.298 秒，无跳过；
匹配 native capture 插件启用。make demo 与 git diff --check 通过；
新增真实 Clang 测试在 Clang17 和 SDK Clang23 各 5 项通过。
本轮未启动 GPU、未重新编译 softmax kernel，
未核验远端 CI。下一步应定位循环体拒绝的精确 AST，而非直接放宽白名单。
