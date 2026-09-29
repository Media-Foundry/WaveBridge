# 外部保位协议下的枚举相等检查

基线f0583d2，分支wb03-source-ast。目标是补齐“转换后相等”到“源枚举值
相等”的条件推理，不冒充已验证的ABI、lowering或API成功。

## 为什么不是枚举常量范围

[C++枚举规则](https://eel.is/c++draft/dcl.enum)区分枚举值范围与表达式可能
具有的值；named constants最大值不能直接充当所有运行时API返回值的上界。
本轮没有推导`[0,1055]`域，也没有把一次UINT_MAX探针当成完整转换规律。
[Clang说明](https://clang.llvm.org/extra/clang-tidy/checks/bugprone/narrowing-conversions.html)
记载其unsigned→signed采用two's-complement解释，但文档也不是本次机器码验证。

本地匹配源码revision `8f497e0992fb7513f7f78a6f6b6f1056c375e961`中，
`clang/lib/CodeGen/CGExprScalar.cpp`的CK_IntegralCast进入EmitScalarConversion；
SrcTy==DstTy支路（约1720行）可能插入检查，然后返回Src。文件SHA256：
`837f792927e9e13ae2e08684f369438b9e7b5f70ce59b092490ebdefa6dee552`。
这项源码检查为外部协议提供依据，**不证明本次实际cc1或机器码实现了该协议**。

## 明确的外部协议与实际重放

使用上轮原HIP native工件，不重新编译原TU或运行GPU。输入文件为
`artifacts/wb-hip-native-enum-20260930-01/native.json`，SHA256
`fa12da3c302d42e7f949b37cc77be7acf75bb8643987435e3398b29f9db947e4`。
外部协议人为声明，保存在
`artifacts/wb-hip-enum-equality-20260930-01/conversion-contract.json`。
它绑定完整payload hash及精确ID，不是源码自动证明的lowering事实。
协议文件SHA256：`02700ee00455365e032fb0dc8a9117def0b3bf57ef280fff12e9450edcfcb29b`。

```bash
PYTHONPATH=src python -c 'import json; from wavebridge.verification.normal_return_guard import check_enum_equality; p=json.load(open("artifacts/wb-hip-native-enum-20260930-01/native.json"))["payload"]; c=json.load(open("artifacts/wb-hip-enum-equality-20260930-01/conversion-contract.json")); print(json.dumps(check_enum_equality(p,"0x3b52b8d0",c),indent=2))' > artifacts/wb-hip-enum-equality-20260930-01/report.json
```

推理链：fresh guard正常返回必要条件→转换后的int值相等→全域保位及唯一
表示的外部前提→相同源位模式→同一枚举值相等。整数模型覆盖全部32-bit
模式，而非named constants集合；数值保持并未建立。

无协议、错payload/ID/位宽、反转两侧、缺项、额外API成功声明、仅单点证据、
截断模型与不确定表示均保持unknown。完整source/API/部署标志不升级。

实际报告为checked，`conditional_enum_equality_under_external_lowering_assumption=true`，
`actual_lowering_verified=false`、`conversion_contract_verified=false`、API/deploy false。
报告SHA256：`f4a2c3dda25b10a41eb068162cd6260a26b45bb2c18d529024ba6de361dcb86b`。
数学模型域为全部32-bit模式`[0,4294967295]`，不是实际调用的动态值域证明。

专项：Clang23与17各8项真实采集/组合回归通过；整数转换6项通过，其中
2～10-bit全模式枚举核对唯一signed解释及模2^W逆映射。有限枚举是回归证据，
不是代替全域身份映射论证。Sol复核无阻断；demo/diff通过。
沿用原生枚举实录的匹配插件环境运行`make check`：1337项99.428秒通过、
无跳过，日志`/tmp/wb-enum-equality-check.log`。

## 剩余义务

本次没有验证实际lowering、链接API、动态输出效果、可达性/正常返回或整核。
新入口没有接入自动部署driver，也没有将外部转换协议自动启用。
下一步应将该条件与同次查询返回值链精确组合，再单独绑定API输出契约；
不能把“返回值等于名为success的常量”直接解释为某个对象已正确初始化。
