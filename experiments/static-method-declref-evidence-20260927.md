# 静态 method 直接引用身份恢复

基线 20b43e5，分支 wb03-source-ast。修复上一轮定位到的真实调用形状缺口，
不实现无写、返回值、正常完成或完整跨 lane 语义。

新增 DeclRefExpr → CXXMethodDecl 路径要求：CallExpr、childless lvalue、
精确非空 ID、表达式/stub/同 ID 全部声明类型一致、所有声明 static/nonvirtual。
优先使用显式 desugaredQualType；显式空或 null 不退回 qualType。原 callee
wrapper 转换仍记录未解除义务，不将类型相同当调用参数或结果值保证。
唯一 body 门槛保持；同 ID 多个 body 不任选其一，缺 body 的叶继续 unresolved。

新增 4 项 fixture 与 3 项真实 Clang 测试。GPT-5.6 Sol 独立验证重载精确 ID、
同名不可达 method、非 static/virtual、外部叶边界；fixture 补类型/声明冲突、
隐藏子表达式和重复 body。Clang17/SDK23 新增源码测试各 3 项通过。

## 固定真实 AST 开发重放

```bash
PYTHONPATH=src python3 -m experiments.softmax_constant_followup \
  --ast artifacts/wb-pytorch-softmax-KhwXBa/attempt-02/ast.json \
  --previous-report artifacts/wb-pytorch-softmax-KhwXBa/attempt-02/report.json \
  --output-dir artifacts/wb-static-method-h8gclO/replay
PYTHONPATH=src python3 -m experiments.softmax_call_audit \
  --ast artifacts/wb-pytorch-softmax-KhwXBa/attempt-02/ast.json \
  --previous-report artifacts/wb-column-wrappers-ywAkXI/replay/report.json \
  --output-dir artifacts/wb-static-method-h8gclO/audit
```

报告哈希：

- replay/report.json：`1f58c4d7e8918dde74a9f38bdf59c5f30e2b640d2d5cd19c1135e98a30f39165`
- audit/report.json：`e718b303f2f82a97a60bda8c27dc70c4bf1ea8e5ac10e84f3db6a94c181dd976`

三处 method 调用现在均有 static_method_exact_declref 边：两处指向
0x83d10d0、一处指向 0x83d1228。语法可追踪唯一函数体由 13 增到 15，
调用边 28；未解析项由 12 变成 11，即 9 个无唯一 body 的外部叶和 2 个
unsupported_call_kind。减少 3 个 method 拒绝，同时新增 2 个 builtin 叶。
新增边不是新建纯度结论，不能因 unresolved 数量减少就计算正确性提升。

循环依旧 1 recovered/7 unknown，归约候选仍 0；analysis_complete/checked/
deployable 未升级。现有 body 检查仍拒绝这些调用。这是已见 AST 的开发重放，
不计新 holdout、整核接受或生产 kernel 覆盖；首次冻结报告不改写。

工件/验收日志：artifacts/wb-static-method-h8gclO/。无新前端、GPU 或远端 CI
核验。下一步须为实际外部叶建立显式语义及效果依据，再考虑独立的调用效果
检查；函数名、noexcept、BuiltinAttr 或上述身份边不能代替该依据。
完整 make check 970 项通过（66.349 秒，匹配 native capture 插件启用，无
跳过）；make demo/git diff --check 通过，SDK23 新增源码测试 3 项通过。
