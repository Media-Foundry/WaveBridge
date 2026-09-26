# 交接：整数常量表达式扩展

- 日期、分支、基线：2026-09-27，wb03-source-ast，35cbb1d；开始时工作树干净。
- 用户目标与约定：继续推进真实源码适配；中文回复，直接commit并push，无PR。
- 已完成：integer_constants.evaluate支持具体signed int模板替换literal、非负
  signed移位、比较/条件/逻辑短路；保留类型、范围、未知转换及调用拒绝。
  新增源码/小域/回放测试16项；支持文档、实验实录与status同步。
- 实际验证：固定历史softmax AST开发回放自动得到128/32/4/2；8循环仍unknown，
  首拒绝变为increment_not_plus_equal；归约0候选/12未解析调用。未改冻结结果。
  工件artifacts/wb-constant-expressions-RkmZqE/replay/report.json，SHA256
  63cb6212ff3b3e1087e24047088e634eaf02688565c090b448b99a236eaa3525。
- 测试：919项CPU测试66.723秒全通过，无跳过，匹配native插件启用；demo及diff
  通过。新增真实表达式专项Clang17、SDKClang23均通过；Clang18远端CI未核验。
  CPUoracle仅执行合法源码；负/越界移位等另外源码只采集AST。
- 未执行：GPU、候选、性能、真实kernel重新编译、独立留出评估。
- 保证范围：依赖可信Clang替换literal与显式int_bits，不验证模板实例化/ABI；
  evaluated不代表checked。移位是保守子集，1<<31拒绝不表示普遍UB。
  本次是已知softmax target开发反馈，不是新的研究算法或整核支持证据。
- 协作：GPT-5.6 Sol独立编写真实Clang/CPU测试并复核；主代理实现求值/回放/单测。
- 未提交/未推送：本文件写入时待验收后commit/push，最终状态以git为准。
- 下一项：规范处理typed signed int的++递推，保留body修改/别名/溢出拒绝；
  随后继续从真实AST识别嵌套循环、数组与functor等剩余缺口，不能以局部常量
  恢复宣布G2或GPU适配闭环通过。
- 阻塞：本轮无执行阻塞，严格谱系与强baseline差异等研究门槛仍未建立。
