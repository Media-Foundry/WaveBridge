# 所选配置槽与条件复制字段的精确绑定

基线 `8b0f13b`，分支 `wb03-source-ast`。本轮不生成新候选、不执行HIP/GPU，
不改变已冻结的guard候选或数值协议。

## 新增检查义务

上一轮得到了所选copy的模型内字段区间，但尚未证明它就是所选launch的
配置槽。新增入口从fresh launch报告中的精确位置取出直接constructor，
自动将其ID交给fresh构造/全部引用保持检查，然后核对按值parameter target
确实属于同一configuration CallExpr、同一callee和同一argument position。
父报告绑定全部选点、协议、ABI、预算与输入工件hash，不接收外部成功报告。

position 1仍只是语法槽位；它的block运行时含义没有由此证明。其它配置
实参、API/ABI实际实现、调用可达性、runtime provenance和GPU部署均未验收。
不能据此把外部条件模型升级成真实程序整体保证。

## 实际重放命令

```bash
mkdir -p artifacts/wb-hip-configuration-copy-20260930-01
PYTHONPATH=src python - <<'PY' > artifacts/wb-hip-configuration-copy-20260930-01/report.json
import json
from wavebridge.verification.launch_binding import check_guarded_configuration_copy
p=json.load(open('artifacts/wb-hip-query-guard-candidate-20260930-01/native.json'))['payload']
r=json.load(open('artifacts/wb-hip-source-guard-20260930-01/report.json'))
s=json.load(open('artifacts/wb-hip-guard-target-20260930-01/report.json'))['selection']
abi={'int':{'bits':32,'signed':True},'unsigned int':{'bits':32,'signed':False}}
print(json.dumps(check_guarded_configuration_copy(p,s,'0x77692424bac0','0x77692424bda8',
 '0x77692424bfb8','0x77692424c3c0',r['selection'],r['conversion_contract_assumed'],
 r['output_contract_assumed'],abi,query_guard_id='0x77692424bc18',
 configuration_position=1,instantiated_function_id='0x2d7f1410'),indent=2))
PY
```

旧报告只读取选点与外部契约，不读取通过结论。输入native SHA256
`df7d0b37e1d7ca16977f6d133285705d004a655e880b87b635148a373816e8b5`；
launch选点来源文件SHA256
`34d20ae4506ee9727d3ad8cb9f1e6c5ee7115467656f7be5bb52e082bd651297`；
源码数值选点/外部契约来源文件SHA256
`771f1a83bcc2c30b524f38a4245034bae47cd6558db99f5becb72285d0dae378`。
冻结实现launch_binding.py SHA256
`2e79d48896fefc33b24ee1501b15c8a269a4adf8fbfe9077a7d438e8b37707b6`。

## 回归与复核

新fixture是合成CUDA host-only语法测试，不是生产GPU实验。真实Clang AST
经完整数值/复制/launch链，未mock恢复器：正常slot1、合法slot0、错误位置、
字段改写、另一launch、反转四槽、旧root hash、非法位置与预算均有回归。
在slot0得到条件字段，不意味着把slot0改称block；这用于确认位置绑定不猜角色。

Clang23新专项4项23.256秒、Clang17新专项4项28.005秒通过。后续增加父子
输入hash及conditional字段断言，纳入冻结全测；未改变checker实现。
日志 `/tmp/wb-config-copy-tests.log` 与 `/tmp/wb-config-copy-clang17.log`。
Sol只读复核未发现跨层错绑或范围膨胀；demo/diff通过。

冻结 `make check` 全部1386项通过，293.843秒，无跳过；日志
`/tmp/wb-config-copy-check.log`。沿用固定环境：native capture为Clang17，
visibility/unary/using-shadow/enum为Clang23。该全测包含最后补充的hash及
conditional字段断言。本轮没有解决此前完整Clang23 capture专项的兼容性缺口。

## 最终真实工件

报告为条件checked，SHA256
`766d587f53aba0678442e554f506eeeecadb0d6a9aa9310c2055320e3b47967b`。
kernel `0x7769241d57f0`、launch `0x7769241d5b08`，配置CallExpr
`0x7769241d4bb8`调用callee `0x2caec780`。所选position 1确实绑定参数
`0x2caec560`及copy `0x7769241d4cc8`，三个FieldDecl区间为32/4/1。
内部fresh用途检查仍覆盖全部22copy，未为选中槽裁剪其它引用。
launch API、全部配置实参、执行、runtime provenance、source/deploy标记均false。
结束后实现SHA256与冻结值一致，没有以旧报告替代重放。
