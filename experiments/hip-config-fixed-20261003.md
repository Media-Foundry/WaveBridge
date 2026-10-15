# Fresh配置派生域连接普通内层入口

基线9d97bac，2026-10-03。真实HIP候选未改动，无新GPU运行。

## 本轮改变的保证边界

旧普通嵌套重放从旧报告读取leaf域作为外部输入，本轮不再读取该域。
新入口check_guarded_coordinate_to_fixed_nested_entry重新执行：
配置槽绑定、守卫构造及对象复制保持、三轴配置派生local-ID域、真实getter
初始化、到outer之前的历史、普通固定两层循环及完整调用效果检查。
配置字段/数值域不是协议手填，native报告和所有子输入哈希在本次调用内闭合。

parent核对root、native envelope、kernel owner、所选局部/outer/inner、
result interval、完整history输入、header/ABI、work协议和预算。
所有上游前提合并保留，fresh_configuration_composed只描述本次重新组合，
不表示运行时配置或API实现已经验证。hardware_limits/thread_participation、
reachability、body completion、column coverage、source/deploy标志仍false。

## 固定输入与重放命令

native SHA256：`df7d0b37e1d7ca16977f6d133285705d004a655e880b87b635148a373816e8b5`。
使用既有axis API身份协议，不按字段名猜测坐标角色。
旧报告仅提供选点和明确的外部契约（包括UNVERIFIED builtin效果），
不读取旧成功状态、旧leaf域或旧循环保持结论。

```bash
mkdir -p artifacts/wb-hip-config-fixed-20261003-01
PYTHONPATH=src python - <<'PY' > artifacts/wb-hip-config-fixed-20261003-01/report.json
import json
from wavebridge.verification.block_configuration import check_guarded_coordinate_to_fixed_nested_entry
p=json.load(open('artifacts/wb-hip-query-guard-candidate-20260930-01/native.json'))['payload']
r=json.load(open('artifacts/wb-hip-source-guard-20260930-01/report.json'))
s=json.load(open('artifacts/wb-hip-guard-target-20260930-01/report.json'))['selection']
a=json.load(open('experiments/hip-guard-coordinate-api-20260930.json'))
w=json.load(open('artifacts/wb-hip-fixed-loading-20261003-01/report.json'))['work_protocol']
abi={'int':{'bits':32,'signed':True},'unsigned int':{'bits':32,'signed':False},'unsigned long':{'bits':64,'signed':False}}
print(json.dumps(check_guarded_coordinate_to_fixed_nested_entry(
 p,s,'0x77692424bac0','0x77692424bda8','0x77692424bfb8','0x77692424c3c0',
 r['selection'],r['conversion_contract_assumed'],r['output_contract_assumed'],abi,a,
 '0x7769241ab3f0','0x7769241acb28','0x7769241acad0',{}, {'0x7769241aca08':w},
 query_guard_id='0x77692424bc18',instantiated_function_id='0x2d7f1410'),indent=2))
PY
```

大AST和原始报告仅保存在本地ignored artifacts，不称为已上传的完整复现包。

## 回归设计与早期失败

真实native CUDA fixture新增普通双层循环正例、inner后修改坐标、其他kernel
inner错绑、unused协议，以及通过实际native builtin元数据绑定的调用正例。
无效果协议时调用应unknown；有明确协议时，子递推仍必须标成依赖外部效果。
此小fixture初用__builtin_inff，现有白名单正确拒绝builtin_structure_not_supported；
正例修正为真实HIP使用且已有支持的__builtin_huge_valf，没有扩白名单或放宽
调用检查。首轮失败日志当时位于/tmp/wb-config-fixed-smoke.log、
/tmp/wb-config-fixed-call-detail.log。它们不是最终通过记录。

## 中断后恢复核验（2026-10-15）

真实报告已完整保存，退出会话已不可用。报告status=checked，
fresh_configuration_composed=true，value_preserved_to_nested_entry=true，
result_interval=[0,31]；两个fresh子检查均checked。API/runtime、硬件限制、
线程参与、可达性、body完成、列覆盖、source/deploy仍全部false。
这不消除报告中记录的外部前提，也不构成完整自动适配验收。

报告SHA256：`5d9e644f5ba502e17c2d4a5c8935abd13014175ac0bf09d45613e3f3c4944de8`。
block_configuration.py SHA256：
`6af60bcbf9fbdaedb3e84ce343e5ba4ac05f50d7d6156fb4814a8a3f499ebeec`，
与启动时冻结值一致。

10月3日Clang17专项曾观测到16项225.273秒通过，但恢复时/tmp测试日志均
已不存在，不能核验旧全量运行的最终状态。故本轮重新运行完整make check及
Clang17专项，日志改存artifacts/wb-hip-config-fixed-20261003-01/，避免依赖/tmp。
旧失败日志目前也已不可读取，上述早期失败经过保留为当时观察，不称现存工件。
本次重新验收：make check共1403项469.787秒，退出0，无跳过；Clang17
专项16项210.340秒通过。日志为上述目录的check-20261015.log和
clang17-20261015.log；demo-20261015.log记录make demo成功，git diff --check通过。
全量沿用固定配置：native capture为Clang17匹配插件，visibility/unary/
using-shadow/enum为Clang23匹配工具链，包含最终版新增回归。
Sol此前只读复核无soundness阻断；建议的native envelope显式核对与硬件/
参与false标志均已落实。未宣称完整Clang23 capture兼容性已建立。
