# 通用整数常量表达式扩展与 softmax 开发回放

日期：2026-09-27；变更基线 `35cbb1d`。这不是新的冻结留出评估。

## 实现与验收边界

扩展现有`analysis.integer_constants.evaluate`，没有新增算子模板：支持可信
Clang具体signed int模板替换literal、非负signed移位、typed bool比较及短路
条件表达式。详见[支持子集](../compiler/analysis/README.md)。位宽仍显式给定。

移位数必须小于int_bits且非负；负操作数、unsigned或超出signed结果范围
均unknown。这比C++17允许的范围更窄，特别是不接受符号位转换：不能把
`1 << 31`的拒绝说成普遍UB。[C++17移位规则](https://timsong-cpp.github.io/cppwp/n4659/expr.shift)
规定移位数边界，并对负数右移保留实现定义行为。

条件先求值谓词，仅求值选中分支；`&&/||`保留短路，不调用死分支函数。
两结果分支仍必须有受支持signed int类型。这一处理遵循
[条件运算符规则](https://timsong-cpp.github.io/cppwp/n4659/expr.cond)，不证明
整份源程序有效，也不支持用户转换或任意constexpr函数。报告记录选中分支及
模板替换literal来源；未独立证明Clang模板实例化或ABI，checked仍false。

7项小域/畸形AST回归与5项真实Clang测试分开保存；后者使用重命名模板及
实际CPU执行作合法表达式对照。非法/实现定义移位只采集AST，单独源码不参与
CPU oracle执行；死分支除零/调用由合法短路隔离。另4项回放driver测试检查
历史工件绑定、不可覆盖、实现漂移与状态边界，不算额外语料覆盖。

## 保存 AST 的开发回放

```bash
PYTHONPATH=src python3 -m experiments.softmax_constant_followup \
  --ast artifacts/wb-pytorch-softmax-KhwXBa/attempt-02/ast.json \
  --previous-report artifacts/wb-pytorch-softmax-KhwXBa/attempt-02/report.json \
  --output-dir artifacts/wb-constant-expressions-RkmZqE/replay
```

入口固定历史AST和report摘要，再使用当前实现fresh调用常量、列循环与归约
恢复。没有重新采集Clang、修改源码或启动GPU；不是原`pytorch_softmax_intake`
冻结协议的再次通过。原冻结结果及报告完全保留。

| 保存CUDA AST中的常量 | 扩展后的自动求值 |
| --- | ---: |
| next_power_of_two | 128 |
| WARP_SIZE | 32 |
| WARP_ITERATIONS | 4 |
| WARP_BATCH | 2 |

driver遍历所选实例的全部constexpr局部声明，不输入上述值或名称作为oracle。
这些是该CUDA编译视图的常量，不是本次测得的GPU物理波宽。

8个循环仍全部unknown，但首拒绝已从`bound_not_parameter_or_resolved_const`
变为`increment_not_plus_equal`（原循环使用`++`）。归约候选仍0、未解析调用
仍12。不能将这4项常量求值等同为8个循环恢复、softmax支持或G2通过。
下一步需在明确类型和循环体副作用前提下处理递增形式；之后仍要面对嵌套循环、
寄存器数组、functor及数值语义，不能预设只加`++`就会通过。

本轮报告 `artifacts/wb-constant-expressions-RkmZqE/replay/report.json` 的SHA256：
`63cb6212ff3b3e1087e24047088e634eaf02688565c090b448b99a236eaa3525`。
输入AST/历史report/当前分析实现及driver前后摘要一致。原始报告和测试日志仅在
本地artifacts保存，实录与代码入git。

这属于必要的通用前端基础能力，不作为新的研究算法贡献；它没有证明相对
Polygeist/CKTI的增量，也未解决严格独立谱系验收。

最终全量`make check`：919项、66.723秒、全部通过无跳过（匹配native插件启用）。
`make demo`与`git diff --check`通过。真实表达式专项5项另在SDK Clang23重跑
通过，版本原文及日志分别保存为`clang-sdk-version.log`、`clang-sdk-tests.log`。
远端Clang18 CI尚未在本轮核验。GPT-5.6 Sol提供独立真实源码测试与只读复核。
