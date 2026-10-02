# 配置派生坐标到首个加载循环之前

基线 `e2535c0`，分支 `wb03-source-ast`。本轮不修改冻结HIP候选，不启动GPU。

## 检查范围

`check_guarded_coordinate_to_statement`重新执行配置/对象复制/坐标初始化链，
把本次派生的leaf域交给既有历史检查器；不接受手填区间或历史通过报告。
核对同root、kernel owner、局部声明、目标语句、区间与完整输入哈希。
所有上游API、对象provenance、正常执行及前缀存储不别名局部的假设完整保留。

所选局部为 `local_idx` (`0x7769241ab3f0`)，目标为真实首个外层加载
`ForStmt` (`0x7769241acb28`)，kernel为 `0x7769241d57f0`。
结论仅到该语句首次开始求值之前：不包含循环头/循环体，不包含后续迭代，
不证明目标可达、列覆盖、参与线程、跨lane等价或部署安全。

## 重放

沿用已冻结native AST与API轴协议，旧报告仅读取选点和外部契约。
native SHA256为
`df7d0b37e1d7ca16977f6d133285705d004a655e880b87b635148a373816e8b5`。
轴协议为 `experiments/hip-guard-coordinate-api-20260930.json`。

```bash
mkdir -p artifacts/wb-hip-coordinate-history-20260930-01
PYTHONPATH=src python - <<'PY' > artifacts/wb-hip-coordinate-history-20260930-01/report.json
import json
from wavebridge.verification.block_configuration import check_guarded_coordinate_to_statement
p=json.load(open('artifacts/wb-hip-query-guard-candidate-20260930-01/native.json'))['payload']
r=json.load(open('artifacts/wb-hip-source-guard-20260930-01/report.json'))
s=json.load(open('artifacts/wb-hip-guard-target-20260930-01/report.json'))['selection']
a=json.load(open('experiments/hip-guard-coordinate-api-20260930.json'))
abi={'int':{'bits':32,'signed':True},'unsigned int':{'bits':32,'signed':False},'unsigned long':{'bits':64,'signed':False}}
print(json.dumps(check_guarded_coordinate_to_statement(
 p,s,'0x77692424bac0','0x77692424bda8','0x77692424bfb8','0x77692424c3c0',
 r['selection'],r['conversion_contract_assumed'],r['output_contract_assumed'],
 abi,a,'0x7769241ab3f0','0x7769241acb28',{},query_guard_id='0x77692424bc18',
 instantiated_function_id='0x2d7f1410',use_static_branches=True),indent=2))
PY
```

## 回归与诊断边界

新增真实native CUDA fixture覆盖正例、前缀直接修改、引用别名修改、
未提供效果协议的前缀调用、其他kernel的目标、未消费调用协议和缺失目标。
循环体修改的样例允许“循环之前”checked，但循环求值/循环体/后续迭代
标志始终false。这些是合成前端回归，不是GPU数值证据。

首轮12项测试中两个正例返回unknown：fixture把第二个坐标getter放在
所选局部初始化之后，历史检查器要求调用效果协议。随后按真实kernel
顺序把y初始化置于x之前，并另保留该不透明调用作为unknown负例；没有
放宽调用检查。失败日志保留在 `/tmp/wb-coordinate-history-tests.log`。
最早的真实历史支持性诊断使用假设的[0,31]，不作为配置派生证据。

## 最终验收（2026-10-03恢复后核验）

- `make check`：1394项，406.952秒，无跳过，退出0。日志
  `/tmp/wb-coordinate-history-check.log`；native capture使用Clang17插件，
  visibility/unary/using-shadow/enum使用Clang23工具链，与上一轮固定配置一致。
- Clang23专项12项140.105秒，Clang17专项12项138.588秒，均通过。
  日志分别为 `/tmp/wb-coordinate-history-final.log` 和
  `/tmp/wb-coordinate-history-clang17.log`。
- `make demo`、`git diff --check`通过。Sol只读复核无阻断项。
- 未执行GPU作业；未消除完整Clang23 capture已知兼容性缺口。

真实报告为条件checked，区间[0,31]，history绑定局部声明所在语句序号7与
目标语句序号13，检查中间五条语句。保留全部66条合并前提。
`target_evaluation_checked`、`target_body_checked`、`later_iterations_checked`、
`target_reachability_proved`、`coordinate_API_verified`、
`runtime_configuration_verified`、`source_program_checked`、`deployable`均false。

报告SHA256：
`0e8f0cc5d39c80f6058e2ea5a54ad335c2a5cc8cfdffe0c99451b81ad3738932`。
`block_configuration.py` SHA256：
`3c89a1312ee9e0714535e81bb2c0aa5997c5abac04c784c04dc94645d1c52c92`。
原AST及大报告仍存本地ignored artifacts，不随源码提交上云；命令、身份与哈希
记录入库，不把仅保存哈希称为完整可下载复现包。
