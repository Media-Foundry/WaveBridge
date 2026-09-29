# 查询初值到 minimum 语句首次入口

基线4868466，分支wb03-source-ast。不重新编译原HIP TU、不执行程序/GPU。
本轮重放已有native AST并编译真实Clang回归fixture。

## 检查边界

复用既有历史checker，新增私有stop-at-target-entry模式。fresh getter
初始化生成内部symbolic seed，不输入用户或生成器提供的成功报告。
目标前的protected references和中间语句仍完整检查；target与以后同块兄弟
子树中的引用不用于拒绝首次入口关系，但全函数禁项遍历不被剪枝。
因此later普通写/地址使用不推翻入口关系，later goto/label/lambda/asm等仍
会拒绝，防止把后续回流或捕获遗漏为安全。默认旧入口保持不变。

## 实际命令和绑定

输入`artifacts/wb-hip-native-enum-20260930-01/native.json`，SHA256
`fa12da3c302d42e7f949b37cc77be7acf75bb8643987435e3398b29f9db947e4`。
转换/输出外部协议沿用前两轮，文件分别为
`artifacts/wb-hip-enum-equality-20260930-01/conversion-contract.json`、
`artifacts/wb-hip-query-output-20260930-01/output-contract.json`，SHA256依次为
`02700ee00455365e032fb0dc8a9117def0b3bf57ef280fff12e9450edcfcb29b`、
`61fcd49cf9c1d27373a1406031c39188e0516a54f96a44131a3e4fade2df7e4f`。

```bash
PYTHONPATH=src python -c 'import json; from wavebridge.verification.field_snapshot import check_query_initializer_to_statement; p=json.load(open("artifacts/wb-hip-native-enum-20260930-01/native.json"))["payload"]; c=json.load(open("artifacts/wb-hip-enum-equality-20260930-01/conversion-contract.json")); o=json.load(open("artifacts/wb-hip-query-output-20260930-01/output-contract.json")); print(json.dumps(check_query_initializer_to_statement(p,"0x703be3d5a7a0","0x703be3d5a9d0",c,o),indent=2))' > artifacts/wb-hip-query-history-20260930-01/report.json
```

选点为实例化局部变量`0x703be3d5a7a0`与赋值语句`0x703be3d5a9d0`。
此checker不因我们将语句称为minimum就解释其运算；它只保证到入口的值保持。
真正的minimum transfer须由独立`check_local_minimum_update`重新检查并连接。

实际重放checked：同块起点/目标索引为2/3，中间没有语句；target及以后的
5个引用明确列为excluded，目标自身仍未检查。初值符号关系保持到首次入口。
报告SHA256：`abd617dd7cc470b9985470f0dd66f1f1d5e51e63acef7f7e202b6d998fb91242`；
field_snapshot.py与integer_selection.py SHA256依次为
`689539147a4015f43076c250703d6bffe124db59dc4439a1ad64c5de0a7a0cea`、
`035878838f5b142d8db3699752d6de5b528e67cc460f4117277875aa1de75f74`。

## 回归与未解除义务

Clang23/17各9项专项通过，其中新增3组历史回归覆盖target/later写不影响
首次入口、before写/array地址逃逸拒绝、later goto/lambda拒绝、跨块目标、
预算、错ID及输入不变性。全部API/转换/链接/生命周期前提继续继承。
target_statement_checked=false，runtime_return_interval null，source/deploy false；
不证明分支可达、minimum计算结果、后续launch配置或具体波宽。
Sol只读复核无阻断；demo/diff通过。
沿用原生枚举实录匹配插件环境执行`make check`，1349项104.673秒通过、
无跳过；完整日志`/tmp/wb-query-history-check.log`。
