# 原 HIP 守卫的同次枚举证据绑定

基线 bfbf850，分支 wb03-source-ast。本轮重放原TU已采集AST，不重新编译
该TU，不执行程序或GPU，不把历史W7900结果记作本轮结果。

输入 `artifacts/wb-hip-native-enum-20260930-01/native.json`，文件SHA256：
`fa12da3c302d42e7f949b37cc77be7acf75bb8643987435e3398b29f9db947e4`。
本轮没有修改采集插件。选点是该工件内wrapper精确ID `0x3b52b8d0`，
不是旧driver的ID，也没有通过函数名推导语义。

```bash
PYTHONPATH=src python -c 'import json; from wavebridge.verification.normal_return_guard import check_enum_binding; p=json.load(open("artifacts/wb-hip-native-enum-20260930-01/native.json"))["payload"]; print(json.dumps(check_enum_binding(p,"0x3b52b8d0"),indent=2))' > artifacts/wb-hip-native-enum-20260930-01/guard-binding.json
```

fresh guard与enum binding均checked。参数`0x3b52b7c0`经typedef
`0x3a80ae48`指向枚举`0x3a807358`，guard常量`0x3a8074a8`属于该枚举，
值为0；转换节点为`0x3b52ba68`、`0x3b52ba80`。native记录underlying
unsigned int32、promotion int32，报告不据此反推enum/API成功。

根AST hash为`7a4852c3d572686d9cf1ed37b17efb236b67d2460c01286fa0fd8f98d91ee04c`，
payload hash为`461c7f546c218aeec14d8c7333297599cd9899ed547f0d9ed6a095a257410f00`。
输出文件SHA256为`8f14c15c1a52c2dfaa70b3bb68e0d4d6218bbf2b63e3ef29e7f8ebec7b672221`；
本轮normal_return_guard.py SHA256为
`d7d5425ab0ab089a368d74597e3d9315cf001a6fe9f31a4ff8740e71b115fb76`。

真实Clang17/23的专项均6项通过：3项原生观测、3项新绑定测试；后者包括
缺失/重复记录、错误ID、错误提升、非法位宽/常量、alias缺失、修改guard、
常量归属与预算的mutation负例。mutation是测试，不是实际源程序编译结果。
Sol只读复核无阻断；scoped/fixed等native属性仍按明确的可信前端前提消费，
不声称独立复核全部编译器类型元数据。

沿用上一轮原生枚举实录中的匹配插件环境执行`make check`：1333项、99.460秒、
无跳过；完整日志`/tmp/wb-enum-binding-check.log`。`make demo`及
`git diff --check`通过。插件文件未改变。

剩余义务：完整转换语义、动态API契约/输出效果、可达性、正常返回与整核
正确性。固定旧HIP driver尚未切换到新工件，不因本次局部检查放行部署。
