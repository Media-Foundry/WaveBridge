# 查询来源连接到 quotient 初始化

基线`7c05115`，分支`wb03-source-ast`。本轮不编译原HIP TU、不执行程序或GPU。
重放同一完整native AST；回归fixture另由Clang17/23编译为真实AST。

## 边界

`check_query_power_quotient`fresh重跑来源minimum和既有minimum→quotient
检查。精确核对分母声明、assignment/function、minimum状态关系及输入hash，
再把来源关系代入除法。没有从旧报告拼接成功状态，也未输入API数值域。

结果仍以分母非零为条件；`unresolved_obligations`完整继承，
`division_safety_established=false`、`launch_dimension_usable=false`。
非负signed-int常量numerator来自源码，非零未被误当作已证明。
不证明后续quotient历史、构造转换、launch或GPU行为。

## 重放命令

```bash
mkdir -p artifacts/wb-hip-query-quotient-20260930-01
PYTHONPATH=src python - <<'PY' > artifacts/wb-hip-query-quotient-20260930-01/report.json
import json
from wavebridge.verification.field_snapshot import check_query_power_quotient
p=json.load(open('artifacts/wb-hip-native-enum-20260930-01/native.json'))['payload']
c=json.load(open('artifacts/wb-hip-enum-equality-20260930-01/conversion-contract.json'))
o=json.load(open('artifacts/wb-hip-query-output-20260930-01/output-contract.json'))
s={'caller_id':'0x3b97a548','local_id':'0x3b97ac08','guard_id':'0x3b97fea8',
   'call_id':'0x3b9f40e8','callee_id':'0x3b9f3e00','argument_position':2,
   'exponent_id':'0x703be3d5a580','power_id':'0x703be3d5a680'}
print(json.dumps(check_query_power_quotient(p,'0x703be3d5a7a0','0x703be3d5a9d0',
                  '0x703be3d5abe0',s,c,o),indent=2))
PY
```

native输入SHA256：
`fa12da3c302d42e7f949b37cc77be7acf75bb8643987435e3398b29f9db947e4`。
两项外部协议SHA256依次为
`02700ee00455365e032fb0dc8a9117def0b3bf57ef280fff12e9450edcfcb29b`、
`61fcd49cf9c1d27373a1406031c39188e0516a54f96a44131a3e4fade2df7e4f`。
它们是条件协议，不是本轮新验证的API语义。

## 验收范围

新增组合正例，以及minimum后改写、数组地址逃逸、换分母的真实源码负例。
三个负例的origins均checked，随后quotient历史/除法检查unknown，
因此测试确实覆盖第二段边界，而非仅在更早的协议层拒绝。
另覆盖跨函数/缺失quotient、缺协议、预算和输入不变性。
GPT-5.6 Sol只读复核未发现阻断性问题。

Clang23专项15项16.386秒、AOCC17专项15项16.675秒均通过。
完整1355项CPU测试116.742秒通过，无跳过，日志
`/tmp/wb-query-quotient-check.log`；沿用Clang23 visibility/unary/using/enum
与AOCC17 native插件组合。`make demo`和`git diff --check`通过。

冻结field_snapshot.py SHA256：
`2756b9b71053d7643e22d254116dbafdaafd86b8ff288619a8dd0c51c77aa1de`。
integer_selection.py未改，SHA256仍为
`035878838f5b142d8db3699752d6de5b528e67cc460f4117277875aa1de75f74`。

## 实际原HIP结果

组合及origins/quotient均checked；query-origin保持到minimum后，再保持到
`warps_per_block`初始化`0x703be3d5abe0`中的除法`0x703be3d5acd8`。
numerator为源码128，分母为`min(同次query值,128)`；按向零截断整数除法。
非零义务仍为established=false，division safety、launch可用性及deploy均false。
报告SHA256：`43931e708ef6660a654a3a3f2f65253a2c08084ff6ca3fb3d173e27e30105ebc`。
下一步需要可明确接受、精确绑定目标设备/查询调用的数值协议；历史测得32
不能被自动升级成所有执行的API域证明。旧profile driver尚未整体迁移。
