# 查询后置字段到 getter 返回值的条件关系

基线5407355，分支wb03-source-ast。重放已有真实native AST，不重新编译原TU、
不执行程序或GPU。Clang专项仅编译测试fixture。

## 外部协议依据与边界

本地固定SDK `hip_runtime_api.h`的2513～2526行描述设备属性查询的输出参数。
SHA256为`eedd1d07748a1fce0bea08c1f3c41ce8150b1c7c5cc7058e6605d178aa5773e7`。
该注释支持把属性指针作为输出接口来建模，**不验证运行库实现、所有调用
前提、实际deviceId、内存有效性或字段在查询后的稳定性**。

本轮人为给定的输出协议显式包括完整调用后置状态、全部实参/API前提、
alias/layout/alignment及对象可读写/生命周期、保持到read和链接实现义务。
它不包含width=32/64，不假定API名或status常量名本身具有证明力。
协议只作外部前提，报告`external_API_protocol_assumed=true`而verified false。

## 输入和实际命令

原native文件`artifacts/wb-hip-native-enum-20260930-01/native.json`，SHA256
`fa12da3c302d42e7f949b37cc77be7acf75bb8643987435e3398b29f9db947e4`。
转换协议沿用`artifacts/wb-hip-enum-equality-20260930-01/conversion-contract.json`，
SHA256 `02700ee00455365e032fb0dc8a9117def0b3bf57ef280fff12e9450edcfcb29b`。
输出协议位于`artifacts/wb-hip-query-output-20260930-01/output-contract.json`。
SHA256：`61fcd49cf9c1d27373a1406031c39188e0516a54f96a44131a3e4fade2df7e4f`。

```bash
PYTHONPATH=src python -c 'import json; from wavebridge.verification.field_snapshot import check_query_output; p=json.load(open("artifacts/wb-hip-native-enum-20260930-01/native.json"))["payload"]; c=json.load(open("artifacts/wb-hip-enum-equality-20260930-01/conversion-contract.json")); o=json.load(open("artifacts/wb-hip-query-output-20260930-01/output-contract.json")); print(json.dumps(check_query_output(p,"0x3b52ce28",c,o),indent=2))' > artifacts/wb-hip-query-output-20260930-01/report.json
```

getter `0x3b52ce28`，紧邻wrapper `0x3b52e9c8`、query `0x3b52e348`，
输出形参`0x3aca1820`对应实参0的`&object`表达式`0x3b52e218`；object为
`0x3b52cf00`、field为`0x3a803830`、读取`0x3b52ea68`。
实参1的精确形参/表达式为`0x3aca18a0`/`0x3b52e380`，同样绑定，
没有把其值或前置device查询正确性自动视为已建立。

实际重放checked，条件性output-to-return为true，external协议assumed true；
协议/输出verified false、field_numeric_domain null、deploy false。
报告SHA256：`f38f061aba1dbafae827f3daffc40dc212e8c59d5a6c7688f7725312751afb86`；
field_snapshot.py SHA256：`d59466b45fc2d3e7e84f35bf649fdca9b7baf5eb0a4b4dd74f7e664d2f5c1043`。

## 验证与剩余义务

Clang23/17各3项专项通过。正例覆盖输出位置0及1；负例覆盖全部协议字段缺失、
错误位置/field/status、非确定输出、额外数值域、错对象、间隔调用、指针别名、
多输出候选、返回值丢弃、预算和不可变性。协议测试是人为前提，非API实现验证。
Sol只读复核无阻断，demo/diff通过。
沿用原生枚举实录的匹配插件环境执行`make check`：1343项102.292秒通过、
无跳过。完整日志`/tmp/wb-query-output-check.log`。

`field_read_validity`仅被外部API后置状态/生命周期/保持协议条件性供应；
counter-defined等子前提继续保留。结论不证明API实现、动态内存、设备选择、
波宽值、可达性或整核等价，不进入部署门控。
