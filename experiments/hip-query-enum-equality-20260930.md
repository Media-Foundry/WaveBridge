# 同一次查询返回值的条件枚举相等

基线1c81d4a，分支wb03-source-ast。本轮不重编原HIP TU，不运行程序或GPU。
只重放已有真实native AST，另编译真实Clang测试fixture。

## 输入与选点

输入`artifacts/wb-hip-native-enum-20260930-01/native.json`，SHA256
`fa12da3c302d42e7f949b37cc77be7acf75bb8643987435e3398b29f9db947e4`。
显式外部协议沿用
`artifacts/wb-hip-enum-equality-20260930-01/conversion-contract.json`，SHA256
`02700ee00455365e032fb0dc8a9117def0b3bf57ef280fff12e9450edcfcb29b`。
协议未被验证为实际lowering事实，本轮没有扩大其保证。

从新AST定位API宽度helper定义`0x3b52ce28`，其中两个wrapper调用分别为
`0x3b52e138`和`0x3b52e9c8`，嵌套query分别为`0x3b52e070`和`0x3b52e348`。
定位使用源码名字仅用于导航；检查入口使用精确ID、重新绑定direct callee，
不按名字判断API成功或输出作用。

两处实际重放均checked，精确query声明分别为`0x3aca0830`和`0x3aca19c8`。
只有条件性query枚举相等为true，API成功、输出效果、部署仍false。
报告SHA256：`8670c339b6d4e1e2fab9264f99fee2277e74edcc69a612c5e4c72ab47f53c4d7`；
本轮normal_return_guard.py SHA256：
`ab59e650bc57febd7e1b29f25d4e94684ab1863862ebd674140bac4ccccaa7f8`。

```bash
PYTHONPATH=src python -c 'import json; from wavebridge.verification.normal_return_guard import check_call_enum_equality; p=json.load(open("artifacts/wb-hip-native-enum-20260930-01/native.json"))["payload"]; c=json.load(open("artifacts/wb-hip-enum-equality-20260930-01/conversion-contract.json")); print(json.dumps([check_call_enum_equality(p,i,c) for i in ("0x3b52e138","0x3b52e9c8")],indent=2))' > artifacts/wb-hip-query-enum-equality-20260930-01/report.json
```

## 保证与局限

入口重新检查query→wrapper实参保持，并独立fresh检查guard→enum→转换协议。
同root、parameter、constant、两个有序转换节点必须对应；合并调用链接、
noreturn、有效执行、无异步干扰及外部保位/唯一表示假设。
结论只针对这一次实际返回值：若wrapper正常返回且全部前提成立，它等于
guard所比较的枚举常量。不是另一次query的结果，更不是输出指针内容保证。

缺协议、错误身份、常量实参、逗号丢弃、转换后实参、条件/间接调用及未检查
wrapper都保持unknown。测试中的AST mutation是负例，不冒充真实源码覆盖。
常量命名、值为0或检查通过，都不能自行建立API成功/输出初始化/设备波宽。

Clang23及17各11项专项通过，其中新增3组query组合回归。两个不同查询的
正例具有不同selection哈希；负例覆盖query形态、协议身份、AST篡改、预算
以及输入不可变性。Sol只读复核无阻断，demo/diff通过。
沿用原生枚举实录的匹配插件环境运行`make check`：1340项100.492秒通过，
无跳过。完整日志`/tmp/wb-query-enum-equality-check.log`。

下一项义务是将这条返回值关系与精确输出对象及独立API输出协议对应。
不得从成功状态推断未知的地址有效性、实际链接实现或已初始化字段。
