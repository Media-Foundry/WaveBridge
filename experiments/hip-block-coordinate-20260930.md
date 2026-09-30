# Host配置字段到device坐标初始化域

基线 `d171a9b`，分支 `wb03-source-ast`。不修改冻结候选，不执行新HIP/GPU程序。

## 为什么不使用旧一维入口

现有 `block_configuration.check` 和 `thread_start_check`针对一维RMSNorm，
要求block `(B,1,1)`；实际softmax配置为二维布局。新增组合保留三个轴，
不将总线程数当作x轴范围，也不把y轴独立行组并入同一归约。

新入口fresh重建配置槽/构造/全部22个引用的条件字段结果，按严格外部API
身份协议映射到x/y/z，再派生所选轴的leaf域，交给既有真实getter/转换检查。
同时限定被检查变量是同一selected kernel的直接自动局部声明。
协议不允许填写数值上下界，因此不再手填local-ID `[0,31]`作为这条链的输入。

## 外部协议不是已验证的SDK事实

`hip-guard-coordinate-api-20260930.json`声明配置参数的字段轴角色、所选
kernel调用对应关系，以及精确external leaf的local-ID语义。它们仍是外部
API/运行时假设，不是依据字段名字、函数名字或一次GPU结果推断出的保证。
绑定AST/参数/record/FieldDecl只能排除错绑，不能证明实现遵守该API。
协议没有维度值、lane范围或待证明的字段保持结论。

新增ABI项unsigned long=64无符号也是显式假设。物理硬件限制、线程参与、
local_idx初始化后的保持、内存访问与跨lane等价、部署均未由本轮建立。
线程总数的乘积仅作数学观察，不作为合法launch规模门槛。

## 真实重放命令

```bash
mkdir -p artifacts/wb-hip-block-coordinate-20260930-01
PYTHONPATH=src python - <<'PY' > artifacts/wb-hip-block-coordinate-20260930-01/report.json
import json
from wavebridge.verification.block_configuration import check_guarded_local_coordinate
p=json.load(open('artifacts/wb-hip-query-guard-candidate-20260930-01/native.json'))['payload']
r=json.load(open('artifacts/wb-hip-source-guard-20260930-01/report.json'))
s=json.load(open('artifacts/wb-hip-guard-target-20260930-01/report.json'))['selection']
a=json.load(open('experiments/hip-guard-coordinate-api-20260930.json'))
abi={'int':{'bits':32,'signed':True},'unsigned int':{'bits':32,'signed':False},'unsigned long':{'bits':64,'signed':False}}
print(json.dumps(check_guarded_local_coordinate(p,s,'0x77692424bac0','0x77692424bda8',
 '0x77692424bfb8','0x77692424c3c0',r['selection'],r['conversion_contract_assumed'],
 r['output_contract_assumed'],abi,a,'0x7769241ab3f0',query_guard_id='0x77692424bc18',
 instantiated_function_id='0x2d7f1410'),indent=2))
PY
```

旧报告仅供选点和外部协议，全部检查fresh执行。原native SHA256
`df7d0b37e1d7ca16977f6d133285705d004a655e880b87b635148a373816e8b5`不变。
axis协议SHA256：`2f83285c043f865ef695206217e700f1327d3708e791a2ebb4b4173b71a61654`。
block_configuration.py SHA256：`fb842a3c06dfac5e186d2df0ff540f92b5f64a4100fe47efafb8b7cc56208423`。

## 诊断与回归

实施前仅用假设的[0,31]做过check_source诊断，确认当前HIP getter和转换在
既有支持子集内；该诊断不是从配置派生的结果，不作最终组合证据。
实际选择的local_idx ID为`0x7769241ab3f0`，getter `0x2d316238`，leaf
`0x2d313928`，均来自同一完整AST，不按函数名字决定值。

合成native CUDA fixture新增真实device getter的x/y两轴。正例分别派生
[0,31]和[0,3]；错误owner/axis/字段/参数/leaf/返回类型以及额外数值键、
旧root和预算均应保留unknown。交换字段角色的测试仍可条件checked，但得到
交换后的域并保持API_verified=false，防止代码暗中按字段名字覆盖协议。
Clang23首轮8项62.384秒通过；随后补leaf/返回类型错绑和内层数值键负例，
纳入最终专项和全测。Sol只读复核无阻断，demo/diff通过。

## 冻结验收

- 最终Clang17专项8项74.126秒通过，包含所有新增负例；日志
  `/tmp/wb-block-coordinate-clang17.log`。
- `make check`1390项336.992秒全部通过，无跳过；日志
  `/tmp/wb-block-coordinate-check.log`。native capture采用固定Clang17，
  visibility/unary/using-shadow/enum采用固定Clang23，包含最终版本的新增测试。
- `make demo`及`git diff --check`通过。本轮没有新增GPU执行，也没有修复或
  宣称完整Clang23 capture专项的已知兼容性缺口。

## 最终真实结果

报告条件checked，SHA256
`244c413bf898bbf70d52b9f60339001a841db0e50be2a86b776b663cca053741`。
配置三轴为x=32/y=4/z=1，数学线程乘积128。派生leaf调用参数[0]与域[0,31]，
重新检查真实getter后，local_idx `0x7769241ab3f0`的初始化区间为[0,31]。
父报告、配置链和initializer的root hash相同，内层仍fresh覆盖22copy；
getter及整数转换checked，结束时实现与axis协议hash均与冻结值一致。
coordinate_API_verified、runtime_configuration_verified、hardware_limits_checked、
coordinate_history_checked、thread_participation_checked、source_program_checked、
deployable全部false。结果不证明全kernel覆盖、后续使用或数值等价。
