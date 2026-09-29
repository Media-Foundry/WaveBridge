# Host 局部初始化与本次 getter 调用

基线8387692，分支wb03-source-ast。本轮只重放原HIP native AST并编译测试
fixture，不重新编译原TU、不运行程序/GPU。

## 输入与选点

输入`artifacts/wb-hip-native-enum-20260930-01/native.json`，SHA256
`fa12da3c302d42e7f949b37cc77be7acf75bb8643987435e3398b29f9db947e4`。
转换/输出外部协议分别沿用
`artifacts/wb-hip-enum-equality-20260930-01/conversion-contract.json`和
`artifacts/wb-hip-query-output-20260930-01/output-contract.json`；SHA256依次为
`02700ee00455365e032fb0dc8a9117def0b3bf57ef280fff12e9450edcfcb29b`、
`61fcd49cf9c1d27373a1406031c39188e0516a54f96a44131a3e4fade2df7e4f`。
协议仍是外部前提，不是本轮对实际运行库/编译lowering的证明。

选中的实例化局部VarDecl是`0x703be3d5a7a0`，直接getter CallExpr为
`0x703be3d5a820`。getter定义`0x3b52ce28`从实际callee引用精确解析，
不是根据warp_size名字填入预设返回值。

```bash
PYTHONPATH=src python -c 'import json; from wavebridge.verification.field_snapshot import check_query_initializer; p=json.load(open("artifacts/wb-hip-native-enum-20260930-01/native.json"))["payload"]; c=json.load(open("artifacts/wb-hip-enum-equality-20260930-01/conversion-contract.json")); o=json.load(open("artifacts/wb-hip-query-output-20260930-01/output-contract.json")); print(json.dumps(check_query_initializer(p,"0x703be3d5a7a0",c,o),indent=2))' > artifacts/wb-hip-query-initializer-20260930-02/report.json
```

模板与实例化共享callee叶`0x3b969ba0`，但其CallExpr和VarDecl不同。
实现只局部支持一致的共享callee leaf occurrence；其他选择节点必须唯一。
所有共享叶的引用声明/类型/category须一致，冲突保持unknown，位置差异不
用于赋予语义。没有全局放松AST身份规则。

首次01重放因只支持函数顶层声明而unknown，文件保留，SHA256
`b400aec81ece6c3e9c80207eeb8de01d0e2e62024a56637f3d21021ff11f9266`。
实际祖先是FunctionDecl→Compound→IfStmt→Compound→DeclStmt，故扩展为
逐项唯一核对的普通块/if路径。只因初值关系以初始化完成为条件才允许这一
扩展；没有跳过词法检查，也没有据此声称if分支实际进入。

最终02重放checked，owner `0x3b9f3e00`，DeclStmt `0x703be3d5a848`；
词法路径从内向外为CompoundStmt→IfStmt→CompoundStmt，共享callee叶出现2次。
history false、runtime interval null、deploy false。最终报告SHA256：
`25cc562202a53e5f5427de41bfbace7cae81398e14add69aea241f9d41c747ed`；
field_snapshot.py SHA256：
`1ae40f6078a0335e60f35773b6d2f4ddbf7984a439d7cbe71461a1728db27845`。

## 验证与边界

Clang23/17各6项专项通过。新增回归包括两个getter、模板原型/实例化共享叶、
不一致引用和重复变量ID，以及static/TLS/const/long/comma/函数指针/多声明/
异常上下文拒绝，普通块/if的唯一词法路径得到记录，但不证明分支可达。
正例中初始化后又改写local，报告仍仅描述初始值，
`history_preserved_to_use=false`，不能据此给minimum/launch使用点签发结论。

getter的全部API/转换/生命周期假设继承，并另保留本次调用执行所选定义、
初始化正常完成的前提。不证明可达性、纯度、运行时链接、后续保持或数值域。
原固定driver尚未升级使用该新工件，不放行部署，也不默认32/64。
Sol分别复核直接调用绑定与最终块/if扩展，无阻断；demo/diff通过。
最终沿用原生枚举实录匹配插件环境执行`make check`：1346项102.342秒通过、
无跳过；日志`/tmp/wb-query-initializer-check-02.log`。首版全量日志另保留，
不作为最终扩展的验收替代。
