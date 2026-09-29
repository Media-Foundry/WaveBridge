# HIP API 状态类型的 compile-only ABI 观测

基线 `d2ed48d`，分支 `wb03-source-ast`。本轮没有修改 checker 的接受结论，
没有执行编译出的程序或 GPU，也没有新增属性值/性能保证。

## 为什么不能从错误码清单直接推导成功

此前已获得 `normal return ⇒ converted comparison is false`，但要把它解释为
API 成功，还需要确认转换与 API 契约，而不能只凭 `hipSuccess` 的名字。
[C++ 枚举规则](https://eel.is/c++draft/dcl.enum) 区分底层类型、枚举值及命名
枚举常量；其值域规则也不能直接用作所有运行时表达式的界限。因此本轮没有
采用“所有错误码不超过 1055，所以任意返回值都不超过 1055”的推论。

新增 compile-only probe，包含本机 SDK 头文件，以 Clang 常量求值记录类型
性质。它是另一个 host TU 的观测，不是原 kernel TU 的 ABI 证明，更不是
运行库的 API 实现证明。`original_kernel_TU_ABI_binding=false`，
`runtime_enum_domain_established=false`，`API_success_verified=false`。

## 实际命令

```bash
PYTHONPATH=src:. python -m experiments.hip_api_abi_probe \
  --compiler /home/husrcf/anaconda3/lib/python3.12/site-packages/_rocm_sdk_core/lib/llvm/bin/clang++ \
  --include artifacts/toolchains/sdk-view-sx4rmd37/include \
  --output artifacts/wb-hip-api-abi-20260930-03/report.json
```

实际为 C++17、`-D__HIP_PLATFORM_AMD__=1`、`-fsyntax-only`，没有 HIP API
运行调用。collector 同次生成依赖清单，并保存工具链 trace、AST 与源码/编译器
哈希。头文件内容是编译后观测，不是冻结快照或依赖完整性证明；该限制原样保留。
最终入口要求 toolchain_trace.status=observed，否则顶层 unknown；此 trace
仍是编译器 dry-run 的计划作业信息，不证明实际 AST 进程身份。

## 结果

| 编译器常量观测 | 结果 |
| --- | --- |
| int 位宽 | 32 |
| hipError_t 位宽 | 32 |
| 底层类型位宽 | 32 |
| 底层类型是 unsigned int | true |
| hipSuccess 转 int | 0 |
| hipErrorTbd 转 int | 1055 |
| unsigned int 最大值转 int 等于 -1 | true |

最后一项只是单个编译器常量表达式观测，不是一般转换规则、单射性或所有
运行时输入上的证明。1055 只是所选命名枚举常量值，不能填入 runtime 输入域。

最终 03 报告 SHA256：`c6e444a8ed59102717099965ec59f29ee6375b3aa76722b0fb208deee64b475d`。
编译器 SHA256：`f80bad7383249331b12bd9bfdfdfe821a9d362393d08e9489d5976681e9e4616`。
源码 SHA256：`e13ce84a51431e09deb592e80806ce79328f70b4fe9568bf35cfc47781d1679f`。
依赖 manifest SHA256：`11b226d66c164e29ee7163e3139862d4007aba83430c11ca9c20b6f43227ddd6`。

01 工件保留：初版解析器没有处理 Clang 的 bool ConstantExpr 字符串 `true`，
返回 unknown；修正 typed bool 解析后产生 02，未覆盖原始失败。
02 SHA256：`bbf06c18910143043508b2e2fa561f99c952bdfedb7d0eba215411c7a2b935ae`。
Sol 复核指出 trace 需要显式门控，随后增加该门控及字段类别/ID 校验，再生成
03；02 作为旧策略观测保留，不冒充最终策略报告。124 个依赖文件记录中，
hip_runtime_api.h SHA256 为
`eedd1d07748a1fce0bea08c1f3c41ce8150b1c7c5cc7058e6605d178aa5773e7`。
4 项测试只测试报告解析器与门控，明确为 fixture，不冒充真实 SDK/ABI 证据。
真实 SDK 证据来自上述单独编译，完整回归在最终补记中记录。

## 下一步边界

绑定 API 契约前，需要把本机类型/转换信息与原 TU 的相同编译输入关联；
API 成功时的输出约定须绑定已恢复的声明、参数、对象和字段，同时保留运行库
实现/链接条件。不能借本轮观测把 query_output_effects 或 width=32 自动设真。

## 最终验收

最终完整 `make check`：1325 项，98.580 秒，无跳过；日志
`/tmp/wb-api-abi-final-check.log`。早期1324项/98.065秒记录仍保留，但不替代
修复后的最终回归。环境沿用SDK Clang23专项、AOCC Clang17旧native capture及
各自匹配插件，普通fixture为PATH clang++。4项定向fixture、make demo和
git diff --check通过。Sol再次只读复核，确认trace门控及字段/身份校验无阻断。
