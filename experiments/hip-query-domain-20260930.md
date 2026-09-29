# 查询数值域：显式假设与算术检查分离

基线`1f2a7c4`，分支`wb03-source-ast`。没有GPU/程序执行，没有重编原HIP TU。

## 证据边界

既有`softmax-hip-pilot-result-20260927.json`记录api_width=32；pilot脚本检查
有限已执行案例的API宽度、device宽度、launch和数值输出。它没有证明所有
后续getter查询都返回32。本轮不将历史观测自动转换成静态输入域。

新增`query-value-domain/v1`外部协议绑定同payload、API输出协议、query具体
调用origin及guarded caller/callee选点。独立算术检查仅回答：如果query值
处于声明域，已恢复的minimum和除法是否安全、商的区间hull为何。
非零义务原样保留，条件解除另列；实际API域和部署标记保持false。

`hip-query-domain-hypothesis-20260930.json`是**明确未验证的[32,32]假设示例**，
不是W7900能力证书。文件没有输入旧成功报告；全部来源与除法链重新检查。
它不代表将研究范围固定为width32，不为native64提供目标执行许可。

## 重放

```bash
mkdir -p artifacts/wb-hip-query-domain-20260930-01
PYTHONPATH=src python - <<'PY' > artifacts/wb-hip-query-domain-20260930-01/report.json
import json
from wavebridge.verification.field_snapshot import check_query_power_quotient
p=json.load(open('artifacts/wb-hip-native-enum-20260930-01/native.json'))['payload']
c=json.load(open('artifacts/wb-hip-enum-equality-20260930-01/conversion-contract.json'))
o=json.load(open('artifacts/wb-hip-query-output-20260930-01/output-contract.json'))
d=json.load(open('experiments/hip-query-domain-hypothesis-20260930.json'))
print(json.dumps(check_query_power_quotient(p,'0x703be3d5a7a0','0x703be3d5a9d0',
    '0x703be3d5abe0',d['power_selection'],c,o,query_domain_contract=d),indent=2))
PY
```

native文件SHA256：
`fa12da3c302d42e7f949b37cc77be7acf75bb8643987435e3398b29f9db947e4`。
协议中payload/output hash是规范化JSON内容hash，不是原文件字节hash。

## 回归范围

纯数学测试枚举4位整数域：numerator=0…7、query所有[-8,7]闭区间，power
集合{1,3,7}，与逐query整数执行比对每个case和整体hull；同时检查含零拒绝。
这是有限测试，不替代一般性论证。负query区间和64位端点、零numerator、
重复/空/非正power、bool、越界域另有测试。
真实Clang组合回归检查精确协议、[32,32]条件商4、域含零、错payload/basis/
scope/getter调用、bool边界，以及非零债务/部署标记不被升级。
Sol只读复核无阻断。消费者须同时检查顶层status与conditional安全标记，
不能仅因符号relation仍true而消费失败的数值检查。

完整1359项CPU测试122.075秒通过，无跳过；日志`/tmp/wb-query-domain-check.log`。
Clang23/17专项各16项19.868/20.399秒通过；纯数学3项、demo/diff通过。
全测沿用Clang23 visibility/unary/using/enum与AOCC17 native插件组合。

冻结实现SHA256：field_snapshot.py
`28e879ec03b4d59445ae4a8f896c224e87f9ed4d0b48cbdf3412338f7d655539`；
integer_selection.py
`6e454b921478c9d1a731cdaffab62b5d8d13001e35f39dab751aef0417b493df`。
假设示例原文件SHA256：
`9e82b08e221efd52341ee6784c97d6956e6a3e4c13f33817bc5a973f1281bc15`。

实际原HIP重放在该外部假设下checked，conditional quotient区间为[4,4]；
`division_safe_under_domain_assumption=true`，但实际division safety、domain
contract verified、launch usable、deploy仍false；原非零义务未删除。
报告SHA256：`f619a82b41b9515944fa695049ee46f3c0d7199158ebf432faaabfe6ed23e4a0`。
这只验证“若query=32”的算术推论，不验证query=32本身。
下一项应为同次query值的源码运行时守卫或可独立核验的目标协议绑定，
而非直接将本示例标记为目标能力证明。
