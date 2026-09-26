# 固定 softmax AST 的调用身份审计

基线 9a944c5，分支 wb03-source-ast。本轮新增可重放的开发诊断 driver，
没有放宽源码恢复器或 checker，也没有取得新的循环接受/GPU/留出结论。

```bash
PYTHONPATH=src python3 -m experiments.softmax_call_audit \
  --ast artifacts/wb-pytorch-softmax-KhwXBa/attempt-02/ast.json \
  --previous-report artifacts/wb-column-wrappers-ywAkXI/replay/report.json \
  --output-dir artifacts/wb-softmax-calls-EamVAt/audit-final
```

最终 report.json SHA256：
`5b02381ab05ba8ba449a53b4d00f6c4c738544b33212fa5de373dc36d85e0fcc`。
driver 同时绑定 AST、上一报告、src 全实现、自身及两个导入的实验 helper
前后哈希。audit/ 是尚未加强 helper 哈希绑定的中间工件，保留不作最终依据。

## 观察到什么

清单沿语法调用引用找到 26 个声明身份、30 个调用位置，其中 17 个身份有
唯一函数体、9 个没有函数体；64 函数预算未耗尽。每条边同时保存生产解析器
原结果、callee wrapper、诊断观察的引用 ID 与原调用 AST。诊断引用不是已
验证 dispatch；所有 effects_checked/dispatch_checked/部署标记仍为 false。
未进入 lambda body，不从调用参数里的函数引用猜 callee，不按函数名绑定。

GPT-5.6 Sol 独立核对到一个具体解析缺口：

| 源码调用身份（仅用于定位） | 精确 method ID | 实际唯一函数体 |
| --- | --- | --- |
| infinity，两处调用 | 0x83d10d0 | 单 return 调用 0x83d22b0 |
| quiet_NaN，一处调用 | 0x83d1228 | 单 return 调用 0x83d2518，参数为空字符串 literal |

两 method 都是 static、`float () noexcept`，调用形状为
FunctionToPointerDecay → DeclRefExpr → CXXMethodDecl。现有 `_callee` 的
DeclRefExpr 路径只接受 FunctionDecl，因此三处均为 indirect_or_unresolved_callee。
末端 0x83d22b0/0x83d2518 分别名为 __builtin_huge_valf/__builtin_nanf，
在同 AST 没有函数体。名称只是诊断标签，不作为返回值或效果证据。

其它观察路径包括 exp → expf → 外部 __nv_expf，log → logf → 外部 __nv_logf，
shuffle wrapper → 外部 NVVM shuffle，以及非 static operator() 和坐标 getter。
这些是语法引用路径，不证明实际动态可达、输入/返回语义、无写或正常完成。

## 下一步由证据决定

先在核心解析器补严格 static-CXXMethodDecl 的直接引用路径：核对精确 ID、
声明 kind/type、无隐藏 callee 子表达式、所有匹配声明均 static/nonvirtual，
保留唯一 body 门槛；冲突/非 static/type 不一致等必须拒绝。然后正常追到
builtin 外部叶，继续 unresolved；独立的 builtin 语义依据仍不可省略。
不把库函数名、noexcept 或 builtin 标签直接等同于无写/正常返回。

新增 4 项 inventory 单元测试涵盖生产解析与诊断分离、重复定义、实参误连、
循环及预算边界；它们是 fixture，不计真实 ML 覆盖。验收日志在
artifacts/wb-softmax-calls-EamVAt/。本轮没有修改 src 核心分析代码、没有
新前端采集/GPU，也未核验远端 CI；原 softmax 整体仍 unknown。
完整 make check 963 项通过（66.917 秒，匹配 native capture 插件启用，无
跳过），新增定向 4 项通过，make demo 与 git diff --check 通过。
