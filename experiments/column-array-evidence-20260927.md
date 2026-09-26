# 多层内建下标写入与索引副作用

基线 acaef51，分支 wb03-source-ast。新增受限存储路径支持，不是一般别名
分析、内存安全证明或真实 GPU 适配。

多层 ArraySubscriptExpr 沿 base 查找直接声明，最多 8 层；每层两个完整
操作数并有 lvalue/类型证据。根声明必须有精确 ID、VarDecl/ParmVarDecl
类型且不是引用。普通 pointer-to-array 的括号只用于类型分类正规化，
不剥离源码中的显式 cast，不绕过缺失 typedef 展开证据。
条件/逗号/cast/重载基址仍拒绝。现有 body 遍历继续检查所有索引与 wrapper。

新增 4 项 fixture 和 4 项真实 Clang 测试：二维局部数组、int(*)[3]、int**
正例；各层索引修改 protected 声明、调用、复杂基址、引用及不完整类型负例。
CPU 仅执行 n=4 的安全正例，输出 `1 13 23 33`。Clang17/SDK23 均运行新增
源码回归；没有执行负例 CPU 程序，也没有 GPU 实验。

```bash
PYTHONPATH=src python3 -m experiments.softmax_constant_followup \
  --ast artifacts/wb-pytorch-softmax-KhwXBa/attempt-02/ast.json \
  --previous-report artifacts/wb-pytorch-softmax-KhwXBa/attempt-02/report.json \
  --output-dir artifacts/wb-column-array-tUmeH9/replay
```

报告 SHA256：`98aef5970ad7deee8edd1b8613fbe6f267a0255288bcbb801083718180233f9c`。
固定真实 AST 的输入/实现/driver 前后哈希稳定。8 个循环仍全部 unknown：
原来的 2 个 unsupported_storage_target 已推进到 call_in_body，另外 5 个
unsupported_body_effect 和 1 个 unsupported_control_flow_in_body 不变。
没有新的成功嵌套证据、整核接受或 holdout；首次冻结结果不改写。

GPT-5.6 Sol 编写真实源码回归并只读复核。早期引用索引负例仅建立引用，
后改为真正通过引用修改索引，并补对称位置用例；最终定向日志单独保留。
完整 make check 948 项通过（65.718 秒，匹配 native 插件启用，无跳过）。
随后强化负例的最终定向 78 项通过（4.476 秒），SDK Clang23 新增源码 4 项
通过（0.098 秒）；make demo 与 git diff --check 通过。
工件/验收日志：artifacts/wb-column-array-tUmeH9/。无新前端采集、GPU 或
远端 CI 核验。下一步需分别处理已观测的模板布尔替换、pragma 包装和调用
语义；不能按函数名称把外部调用直接宣布为纯函数。
