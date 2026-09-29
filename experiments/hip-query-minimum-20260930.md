# 同一 minimum 的查询来源与 power 来源组合

基线`ce9ce76`，分支`wb03-source-ast`。本轮重放已有原HIP native AST，
不重新编译原TU，不执行程序或GPU；真实Clang fixture单独编译为AST。

## 保证范围

`field_snapshot.check_query_power_minimum`在同一调用中重新检查三条关系：
查询字段→getter→局部初始化→minimum首次入口；minimum语法与存储目标；
caller源码守卫→callee参数→power初始化→同一入口。核对精确operand、
target、owner/callee和root哈希，不接受外部成功报告或power数值域。

结果是该选中调用中 `width_after = min(query_value, power_value)` 的条件关系，
其中power_value属于源码派生集合。query_value没有数值域，不把历史API测量32
作为前提，也不由minimum推导正值、除数非零或launch值。外部API/枚举转换协议、
源有效性、动态链接和生命周期等前提完整保留；不证明所有调用或后续状态。

## 重放命令

```bash
mkdir -p artifacts/wb-hip-query-minimum-20260930-01
PYTHONPATH=src python - <<'PY' > artifacts/wb-hip-query-minimum-20260930-01/report.json
import json
from wavebridge.verification.field_snapshot import check_query_power_minimum
p=json.load(open('artifacts/wb-hip-native-enum-20260930-01/native.json'))['payload']
c=json.load(open('artifacts/wb-hip-enum-equality-20260930-01/conversion-contract.json'))
o=json.load(open('artifacts/wb-hip-query-output-20260930-01/output-contract.json'))
s={'caller_id':'0x3b97a548','local_id':'0x3b97ac08','guard_id':'0x3b97fea8',
   'call_id':'0x3b9f40e8','callee_id':'0x3b9f3e00','argument_position':2,
   'exponent_id':'0x703be3d5a580','power_id':'0x703be3d5a680'}
print(json.dumps(check_query_power_minimum(p,'0x703be3d5a7a0','0x703be3d5a9d0',s,c,o),indent=2))
PY
```

输入native文件SHA256为
`fa12da3c302d42e7f949b37cc77be7acf75bb8643987435e3398b29f9db947e4`。
转换与API输出协议沿用此前外部假设，SHA256依次为
`02700ee00455365e032fb0dc8a9117def0b3bf57ef280fff12e9450edcfcb29b`、
`61fcd49cf9c1d27373a1406031c39188e0516a54f96a44131a3e4fade2df7e4f`。
选点来自本轮完整AST，不混用旧AST的指针ID。

## 回归

Clang23与AOCC17各12项native组合回归通过。新增三组测试覆盖完整组合、
真实源码提前写/数组地址逃逸/max负例、缺协议、错operand/callee/call、
ABI/预算/额外伪造结果字段和输入不变性。max实际到达minimum检查后拒绝，
写入与逃逸则在query历史层拒绝。全部测试没有mock三条恢复/检查链。
GPT-5.6 Sol只读复核未发现阻断性问题。

完整1352项测试109.368秒通过、无跳过，日志`/tmp/wb-query-minimum-check.log`；
沿用Clang23 visibility/unary/using/enum与AOCC17 native插件组合。
`make demo`、`git diff --check`通过；没有新GPU数值或性能结果。

冻结实现SHA256：field_snapshot.py为
`b3c1bf12e8352049ba3758d5d684d5ff2a17d8a4933cdffd888682c11574606d`，
integer_selection.py为
`035878838f5b142d8db3699752d6de5b528e67cc460f4117277875aa1de75f74`，
power_ceiling.py为
`0b870c546add3564f19b8d5c71128a2827eaa6f4efcc44ca684f7eef40edb262`。

## 真实重放结果

三条fresh子检查和组合均为checked；源码守卫得到entry集合`{65,128}`，
power为`{128}`，与同次getter查询符号值共同形成赋值后关系。
`query_numeric_domain`、`result_numeric_domain`仍为null，`deployable=false`。
报告SHA256：`dce46e0a3f0684ff7ba0c610a8f63c6c94c7a8200fd94abed564d062bb0dcb1d`。
这不是API宽度验收或自动适配完成；旧profile driver仍未整体迁移到新AST。
