# HIP 输出循环的条件次数边界

2026-09-30，基线`6da8587`。本轮连接已有guarded-work与已有整数区间
检查，新增的生产逻辑仅是显式传递一元/using选项，不替代fresh检查。

## 输入、模式与命令

```bash
PYTHONPATH=src:. python3 -u -m experiments.softmax_unary_work \
  --native artifacts/wb-hip-native-20260927-01/native.json \
  --math-protocols artifacts/wb-hip-native-effect-20260930-01/report.json \
  --zero-protocols artifacts/wb-hip-native-20260927-01/conditional-work.json \
  --iteration-bounds --output artifacts/wb-hip-unary-bounds-20260930-01/report.json
```

三份固定输入SHA同`hip-unary-recurrence-evidence-20260930.md`，没有重新
编译生产TU或启动GPU。mode/schema为iteration-bounds，和recurrence互斥。
选点仍是包含已登记math调用及break的语法循环，非穷尽kernel/循环清单。

驱动先从原AST fresh取得header/guard声明关系，只使用精确声明ID；给除
induction之外的每个guard外部读取声明赋完整`[-2147483648,2147483647]`
区间。该区间是显式int32 ABI范围，不是launch/初始化推断，不声称运行时
实际覆盖全部这些值。最终bounds入口再次fresh检查work/header/guard，并
严格核对区间键，不能把用于选择ID的checked报告当成域正确性的证明。

## 保证边界与测试

次数结果仍以source有效、初始化、存活、不别名、有效实参及未验证leaf
效果/正常返回为前提。nested和work-body算术、完整迭代域、输出覆盖、FP值
与部署不在本轮保证内。`iteration_bounds_established`和
`full_iteration_domain_established`必须分别解读。

真实Clang用完整int32、单点3、非正区间检查保守/精确/零次边界；写入守卫
依赖、实参递增、第二个无协议调用、反序/越界/布尔区间均不放行。驱动
fixture只测试选点/模式/区间参数传递，不作为源码或GPU证据。
GPT-5.6 Sol只读复核未发现阻断。

## 实际结果

进程退出0，observed。输入/src/driver自身hash前后一致，结束后再次与当前
文件核对一致；不声称import辅助脚本或完整Python环境已冻结。报告SHA256：
`05f67b33b9acf236dc2503acadf80d48a97ad07d78ea832b2edaffbc2eab0c18`。

选定外层输出循环`0x745c579c4018`：默认模式unknown，原因为
work_preservation_not_checked；启用模式checked。守卫外部声明
`0x745c579bae48`使用完整signed-int32区间，header最大迭代数2，工作区
执行次数保守界`[0,2]`。i=0和i=1两次比较都保留不确定真值，而不是猜测
全部执行；可能执行的递增也经过有符号可表示性检查。

父报告`iteration_bounds_established=true`，但
`full_iteration_domain_established=false`、source/deploy=false。
work的全部假设与策略hash已向上传递并独立核对；库效果依然unverified。
不能把此结果解释成完整内层循环/数组下标安全、精确行覆盖或输出值保证。

1268项CPU测试通过（104.284秒，无跳过），make demo/diff通过。SDK23
native25项3.726秒、AOCC17 native+driver30项3.813秒、driver5项0.005秒通过。
全量采用新unary/using SDK23与旧native AOCC17匹配插件，不称全量SDK23或
远端CI。日志`/tmp/wb-unary-bounds-{check,demo,targeted,aocc,driver}.log`。
