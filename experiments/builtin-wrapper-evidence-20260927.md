# 完整单返回 wrapper 条件无写入

日期 2026-09-27，基线 ac7bfc1，分支 wb03-source-ast。

新入口在同次完整 native AST 中沿精确声明检查函数体，不将一条 builtin
子调用的结果提升为包围函数结果。受限子集：零参 float free/static 函数，
body 仅一条 return direct-call；内部 callee 类型链及声明一致，最大 32 层。
递归、额外语句、未知调用、复杂返回、参数、非静态/virtual 仍 unknown。
末端 fresh 调用 builtin 效果入口，外部 no-write/正常返回前提保持 unverified。

## CUDA 工件开发回放

输入：artifacts/wb-native-builtins-JR99CL/probe-final.json，SHA256
`ae5cf2a142e6790859a0d4340caa677dae1fc78609ba40f5d0d743f0f7f6aa82`。
回放前核对哈希，并把每个所选末端的协议和结果保存为
artifacts/wb-builtin-wrappers-3uFzg5/replay.json，SHA256
`e0ed1da39372d3e7de004dfaf2ae5eae698d470bb25b30c07be6d91386ed7b3a`。
本轮 builtin_calls.py SHA256：
`1fd208c8cad906bf88c272963b46f9f060e1133fdf064d3f61b0f856e04bab1b`。

| 入口 | wrapper 链 | 结果 |
| --- | --- | --- |
| wb_huge | 0x22946240 | checked，conditional |
| wb_nan | 0x22946450 | checked，conditional |
| wb_limits_huge | 0x229466c8 → 0x21fbff70 | checked，conditional |
| wb_limits_nan | 0x229469d0 → 0x21fc00c8 | checked，conditional |
| wb_store_control | 未接受入口 | unknown，wrapper_signature_unsupported |

回放协议明确写为 demonstration assumption only。没有将先前 IR 观察当作普遍
source 效果证明；这里验证的是已有真实 CUDA AST 上的条件结构组合，不是验证
外部前提，更不是生产 softmax 或 GPU 正确性结果。起始 wrapper 外部调用点的
receiver/参数求值不在结论内。写入探针带参数，因此在签名门槛先拒绝，不能将
该结果单独称为“检测到了函数体写入”。真实 CPU Clang 回归另有零参 global
write 负例，覆盖完整 body 门槛。

## 测试与边界

GPT-5.6 Sol 新增5项真实Clang测试：重命名free/static多层链，写入/逗号返回/
递归/unknown external/参数/instance/virtual负例，错leaf协议，以及32层接受、
33层unknown的精确深度边界。主代理补3项fixture测试：条件范围、声明/额外语句
副作用、身份冲突和预算。测试不把名称当语义依据。

成功不建立返回值、FP环境、纯度、机器码或调用历史；unknown报告中可能保留
部分已绑定声明ID，不能据此升级父级。核心循环门控未改变，尚需检查实际调用
点的完整求值并连接其外部协议，才能讨论循环保持性。
