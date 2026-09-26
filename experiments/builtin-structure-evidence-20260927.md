# builtin 身份与实参结构独立检查

日期 2026-09-27；基线 `875635c`，分支 `wb03-source-ast`。

新增 `verification.builtin_calls.inspect_structure`，fresh 遍历 native envelope
中的完整 AST，核对同一 call、callee、参数 ID 与受限类型/表达式形状。
原生 builtin 身份是可信前端假设；native 名字只选择结构分支，不签发值语义。
只接受零参数 huge_valf 或空字符串 literal decay 的 nanf 结构。
重复记录、AST ID 冲突、缺失 native、普通/间接调用、复杂/非空参数均 unknown。

## 固定 CUDA 工件回放

输入是上一轮 `artifacts/wb-native-builtins-JR99CL/probe-final.json`，
先核对 SHA256 `ae5cf2a142e6790859a0d4340caa677dae1fc78609ba40f5d0d743f0f7f6aa82`。
仅调用其 `payload` 上的新结构入口，三个精确选择为：

| 探针位置 | CallExpr ID | 结构结果 |
| --- | --- | --- |
| wb_huge | 0x229463d8 | checked / no_arguments |
| wb_nan | 0x22946628 | checked / empty_string_literal |
| wb_store_control 中的 builtin 子表达式 | 0x22947388 | checked / no_arguments |

最后一行仅检查 call 子表达式，不检查包围它的函数；函数仍然写内存。
全部报告的 value_semantics/effect_semantics 均为 not_established，
source_program_checked/deployable 均 false，不能据此接受函数或循环。

本地输出 `artifacts/wb-builtin-structure-UQL5sC/replay.json`：
SHA256 `0254660ba62bfc5cc2e746454275e8fb38294c43f04fef517b046a9ffc06df94`。
结构 checker 文件 SHA256：
`ab26bbc853acfcf55ae00e3307855b5ba48e5d748a0c94624d96d57df6ded819`；
复用哈希函数所在 getter_returns.py SHA256：
`f3ec8f64295a37fe39af9b7362674474462b2bc3ba8b8d6bc71beafcdfae99ed`。
这是开发用合成 CUDA 工件回放，不是生产 TU 或独立谱系验收。

## 回归和下一步

新增 5 项手写 fixture 测试；真实 native Clang 测试扩为 6 项，包括实际
`__builtin_nanf("1")`、ordinary external 与函数指针调用，并变异 metadata。
手写 fixture 只检验 checker 分支，不能当作 compiler attestation。
GPT-5.6 Sol 编写真实测试并只读复核，结构正例和负例通过。

当前接口不认证任意调用者传来的 envelope；上层需绑定实际采集报告及工具链
协议。身份、受限实参结构已经能够独立检查，下一步是明确的 builtin 效果/值
协议以及 wrapper 内外表达式组合，不能因本轮 checked 自动开放循环调用。
没有新 GPU 作业、生产前端重采或远端 CI 核验。
