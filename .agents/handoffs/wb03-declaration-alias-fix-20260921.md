# 声明引用类型与存储期修复

- 日期/基线/分支：2026-09-21，fe844b0，wb03-source-ast；中文，直接commit/push。
- 范围：只修改column_loops声明类型分类与induction存储期，不新增分析框架。
  _declaration_is_reference由VarDecl初始化检查和_storage_target共享，优先
  desugaredQualType；别名标识存在但无展开、仍有未知类型名字或类型证据缺失，
  返回unknown。DeclRefExpr的int值类型不能替代被引用声明的int&。
  普通builtin值类型别名可通过；循环头_type不变。static/tls induction拒绝。
- 测试：Sol扩既有真实Clang源码/组合fixture，三种引用别名unknown，真正全局
  using Value=int及只读static_cast<int>正例通过；无mock循环/launch/guard，
  线程坐标报告仍是显式测试前提。手写fixture补充缺失声明type信息，不让
  生产分析器在证据缺失时回退到表达式type。
- CPU witness：三类别名引用各写512/768，值别名写768/768；static/thread_local
  induction跨256次调用各写3列。没有GPU运行或HIP对static/tls支持的主张。
- 验收：make check最终457项通过（4.158秒），git diff --check通过；本机
  AMD AOCC Clang17.0.6。Sol只读审查未发现本次绕过继续放行。
- 重放命令：`PYTHONPATH=src python3 artifacts/wb03-alias-fix-3zAPau/final.py`。
  同真实AST对照git show fe844b0原module与修复module，前三类引用别名旧版
  recovered、新版unknown；普通值别名/只读cast均recovered。报告保留全部
  恢复结果及输入/实现/compiler/runner hash，src运行前后hash一致。
  原HIP AST b9392df4...两个step256循环继续recovered。
- 最终报告SHA256：
  `f38d0ef31263085df90c2d6140e83b0a8c0f99502898d211c698f8c6ab1ed853`，路径
  artifacts/wb03-alias-fix-3zAPau/final/report.json；上层首轮报告保留为历史，
  当时值拷贝fixture仍是int变量，不能算真正值类型别名正例。
- 远端历史核验：gh run view 35522009044 --repo Media-Foundry/WaveBridge
  返回headSha=fe844b0523093490aad86330a3b91d24edbe099c、conclusion=success，
  Clang专项与Python3.11/3.12均成功。新提交CI须另查，不能继承此状态。
- 未完成：全局别名/完整源有效性、独立代码谱系、原始生产TU与编译依赖绑定；
  本次修复不是WB-03整体关闭。下一步冻结已记录子集，回到独立谱系和依赖证据，
  不再围绕当前RMSNorm增加专用分析模块。未运行用户sandbox附件脚本，采用
  仓库真实fixture独立复现。
