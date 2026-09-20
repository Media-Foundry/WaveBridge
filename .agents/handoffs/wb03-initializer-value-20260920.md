# 初始化结果调用连接

- 日期/基线：2026-09-20，wb03-source-ast，12753ca；起始工作区干净。
- 用户约定：中文、直接commit、阶段性push；本轮仅CPU分析，无GPU作业。
- 完成：`analysis/initializer_value.py`连接受限初始化式到结果调用，并在
  initializer_evidence中保存value_link；source报告新增该实现的hash。
  支持无参prvalue直接函数调用及static MS属性getter；不依赖属性/函数名字。
  POE全部语义child中按类型/valueCategory唯一选择结果，不取最后child冒充结果。
  校验三处receiver一致、plain-lvalue引用、exact静态目标、非variadic/无形参、
  允许的callee decay/外层cast；保留转换链与未证明receiver纯度。
- 原理依据：本地LLVM `0b9310c6e4416ee48c07edfef81144e22850dfe7` 的
  `clang/lib/AST/Expr.cpp` PseudoObjectExpr::Create 从result语义表达式取type/VK。
  不声称实际HIP编译器源码已核实；生产者遵循该不变量作为显式外部前提。
- 审查：GPT-5.6 Sol只读审查方案与实现，未发现阻塞性错误；已纳入其提出的
  variadic、括号一致性、prvalue、receiver纯度标注与相关负例。
- 实测：`make check` 323项通过（真实Clang fixture含static属性及改名）；
  `git diff --check`；最终报告全部implementation_sha256与工作树一致。
- 真实HIP命令：
  `PYTHONPATH=src python3 -m wavebridge.source benchmarks/cases/llama-rmsnorm/baseline/rmsnorm_logical32.hip.cpp --compiler /home/husrcf/Code/ProtBind/wavebridge/artifacts/toolchains/sdk-view-sx4rmd37/bin/hipcc --compiler-arg=--cuda-device-only --symbol rms_norm_f32_logical32 --int-bits 32 --output-dir artifacts/wb03-initializer-value-02`
- 最终report SHA256：`330720c92a2b37bcdc7045ae9af82bbf4207b1bc741d4de936aa4bbe8197e66f`。
- 最终AST SHA256：`b9392df45575e1c4bf818ef1bf982c1b0dd2b76e3905f9da0ed6dd05c772a70e`。
- 结果：真实起点value_link recovered，call ID `0x2dc5f718`、getter ID `0x2d2b8c08`；
  unsigned int→const int转换保留未解除义务，checked/deployable=false。
  01为收紧边界前的历史运行，保留但不当作最终实现证据。工件在ignored本地目录。
- 未建立：receiver纯度、外部坐标语义、size_t→unsigned int→int全链值保持、
  运行时launch域、完整源码等价/候选生成。未执行GPU或性能测试。
- 下一步：独立检查getter原始return/callee AST与精确ID链；在显式外部leaf轴/域
  协议及ABI下逐级检查整数转换，再与初始化链和block配置连接。禁止仅看leaf名字
  就认定tid等于thread-x，也不能将模型checked升级为整核部署许可。
- 改动均限实现/回归/协议/状态/本交接；验收后提交推送当前分支，无PR。
