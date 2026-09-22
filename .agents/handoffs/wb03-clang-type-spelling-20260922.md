# 交接：Clang 类型拼写省略与 CI 修复

- 基线：2026-09-22，wb03-source-ast，8b0117d；中文回复、直接 commit/push。
- 起因：远端 run35741316610 的 Python 3.11、3.12 与 Clang 18 三任务失败。
  相同根因产生 3 个 fail/1 个 error：同拼写 desugaredQualType 被省略，导致构造
  身份 unknown，后续测试无法取得关联结果。本地 AOCC Clang 17 输出该键，未暴露差异。
- 修复：只在 desugaredQualType 键不存在时取 qualType；仍经精确 alias→RecordType
  ID→完整 record，且类型打印须相等。显式空/null、不匹配或缺锚点不能通过。
  不全局放宽引用/类型别名检查，不改变默认实参或复制字段保证。
- 依据：LLVM 18.1.8 JSONNodeDumper.cpp createQualType 的 DSQTS != SQTS 条件；
  对应源码链接已写入 compiler/analysis/README.md。
- 验证：make check 532 项；make demo；真实 Clang 专项 65 项通过。
  另以 PATH=/opt/rocm/llvm/bin:$PATH 跑 tests.test_direct_constructor_clang，
  ROCm Clang 23 的 6 项测试通过。此处是 CPU frontend 测试，没有 GPU。
- 回归：在真实 AST 副本上模拟合法的同拼写省略；Clang 23 的 struct Shape 与
  Shape 拼写不同，不能仅删除该字段来模拟合法省略，测试已正确区分。
- 远端验收：修复提交 c1aaf73af519f21bc4d193cd0919f0cf83eefaa2，
  [run35741730545](https://github.com/Media-Foundry/WaveBridge/actions/runs/35741730545)
  已 completed/success；Clang 18、Python 3.11、Python 3.12 三任务均 success。
- 下一步：恢复默认实参工作；必须保留原调用点 AST，将声明来源及参数位置显式
  绑定并让字段 checker 核对，不能把缺源码的 CXXDefaultArgExpr 默认填成 1。

## 下一步默认实参边界（只读核验，尚未实现）

Sol 子代理完成只读核验，主代理对照固定 LLVM 17.0.6 源码：

- [ExprCXX.h](https://github.com/llvm/llvm-project/blob/llvmorg-17.0.6/clang/include/clang/AST/ExprCXX.h#L1140)
  中 CXXDefaultArgExpr 保存 ParmVarDecl 指针，但 JSON 不提供对应绑定。
- [ExprCXX.cpp](https://github.com/llvm/llvm-project/blob/llvmorg-17.0.6/clang/lib/AST/ExprCXX.cpp#L898)
  中 getExpr 可返回 rewritten initializer，不能把所有默认实参等同于参数声明初值。
- [SemaDeclCXX.cpp](https://github.com/llvm/llvm-project/blob/llvmorg-17.0.6/clang/lib/Sema/SemaDeclCXX.cpp#L537)
  会把旧声明默认值复制到新参数。仅见 ParmVarDecl init 不证明表达式原写于该声明。

候选首个支持子集：唯一非模板/非继承构造，无 previousDecl 或其它构造重声明链，
对应直接参数有单一完整 init；先限整数 literal 和已支持转换。保留调用点 AST，
另记默认来源、ctor/param ID 与位置，由字段 checker 核对。模板、继承构造、
重声明、共享/歧义来源及无法排除 rewritten 效果的情况仍 unknown。
这些是下一轮实现约束，不是默认实参恢复已经完成的结论。
