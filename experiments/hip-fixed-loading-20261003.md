# 普通固定次数加载双循环的条件存储保持

基线f390a67，2026-10-03；没有修改HIP候选，也没有GPU执行。

## 实现与保证范围

新增initializer_domain.check_fixed_nested_entry，复用现有真实初始化历史、
普通循环递推和一层固定嵌套检查，而非把原循环改写成带break的形状。
fresh检查outer初始化/条件/增量/body，并保护同一local_idx；inner前后的
兄弟语句也必须保持它，因此结论不限于outer的第一次迭代。
inner必须在重新检查的嵌套位置中唯一出现，AST身份扫描覆盖inner和
array_filler并执行节点预算。全部调用必须fresh检查且协议不得有未消费项。

结论仅为每次实际到达所选inner入口时，局部值保持在声明的初始化域内。
不证明可达性、body正常完成、内存合法性、列覆盖、归约/输出语义或部署。
header序列长度在正常执行前提下成立，不是已测量的执行次数。
内存存储不别名所保护局部或递推变量、源有效性和外部leaf效果仍为显式前提。

## 真实HIP结果

完整native SHA256：
`df7d0b37e1d7ca16977f6d133285705d004a655e880b87b635148a373816e8b5`。
local_idx `0x7769241ab3f0`；outer `0x7769241acb28`；inner `0x7769241acad0`。
本次得到条件checked，结果域[0,31]；outer header序列长2，inner长4。
默认无效果协议时的unknown原始诊断仍保留，不删除或改写。

调用 `0x7769241aca08` 被fresh识别为direct_zero_argument_wrapper；
追踪到builtin调用 `0x2b61f128` 及callee `0x2b61ef60`。
builtin无内存写和正常返回是UNVERIFIED development premise，不是根据
infinity名称或本轮GPU测试建立的性质。外部效果被消费的子递推保持字段
显式标成established_under_external_call_effect_assumptions。

**本次没有重新执行host配置链。**[0,31]取自上一轮已保存的derived_leaf_domain，
仅作为本次checker的外部输入；新历史、getter、循环和调用检查均fresh。
不能把本轮结果与旧配置报告直接拼接成完整配置→全程保持保证。
下一项是fresh组合配置派生域与本入口，再连接列访问/覆盖和线程参与。

## 实际重放

原脚本 `/tmp/wb-fixed-loading-replay.py` 调用方式：

```bash
PYTHONPATH=src:. python /tmp/wb-fixed-loading-replay.py > artifacts/wb-hip-fixed-loading-20261003-01/report.json
```

报告同时记录native哈希、完整leaf域与work协议、fresh_configuration_composed=false
和GPU_executed=false。复现核心调用如下（载入完整原始payload，不裁剪AST）：

```python
from wavebridge.verification.initializer_domain import check_fixed_nested_entry
from wavebridge.verification.getter_returns import _hash
import json
p = json.load(open('artifacts/wb-hip-query-guard-candidate-20260930-01/native.json'))['payload']
old = json.load(open('artifacts/wb-hip-coordinate-history-20260930-01/report.json'))
leaf = old['checks']['coordinate']['derived_leaf_domain']  # external domain only
abi = {'int': {'bits': 32, 'signed': True},
       'unsigned int': {'bits': 32, 'signed': False},
       'unsigned long': {'bits': 64, 'signed': False}}
protocol = {'schema_version': 'builtin-leaf-effect-assumption/v1',
    'native_envelope_sha256': _hash(p), 'call_expression_id': '0x2b61f128',
    'callee_declaration_id': '0x2b61ef60', 'builtin_no_memory_write_assumed': True,
    'valid_call_and_normal_return_assumed': True,
    'evidence_reference': 'UNVERIFIED development no-write/normal-return premise; not SDK or GPU proof'}
report = check_fixed_nested_entry(p, '0x7769241ab3f0', '0x7769241acb28',
    '0x7769241acad0', leaf, abi, {}, {'0x7769241aca08': protocol})
print(json.dumps(report, indent=2))
```

原始大工件仍为本地ignored文件，代码与命令入库不等于完整复现数据已上传。
报告SHA256：`d52c94bdb2f8a1150eded2898ce7924e773640f291bb113c61c637cd8c873240`。
initializer_domain.py SHA256：
`0d5b6765cd6fa793892b1c09b87e93a4be999b830e92a2957cb1e54689704a0b`。

## 回归与复核

新增真实Clang专项5项覆盖普通嵌套正例、inner前/内/后修改、using引用
别名、两层induction改写、header修改、opaque call、break、错误nested身份、
未消费协议、预算和semantic隐藏槽位。没有mock恢复器。
首轮fixture误用过滤AST导致缺失external_leaf，修正为完整TU后正常运行，
未放宽checker。最终专项5项1.170秒通过，连同既有nested/iteration模块15项
2.517秒通过。Sol最终只读复核无阻断，demo/diff通过。
全量make check为1399项415.704秒，无跳过，退出0；日志
`/tmp/wb-fixed-nested-all.log`。采用与上一轮一致的固定工具链：native capture
为Clang17匹配插件，visibility/unary/using-shadow/enum为Clang23匹配工具链。
最终专项日志 `/tmp/wb-fixed-nested-final.log`，相关模块日志
`/tmp/wb-fixed-nested-related.log`。结束后实现和报告哈希与上述冻结值一致。
本轮未执行GPU或宣称完整Clang23 capture兼容。
