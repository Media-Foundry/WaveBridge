# 构造字段到所选复制的条件模型检查

基线 `f73f727`，分支 `wb03-source-ast`。复用冻结的 fail-stop guard 候选；
不重新生成候选、不重新编译 HIP、不运行 GPU。真实 Clang fixture 编译用于回归。

## 新结论和不可省略的边界

新增 `field_snapshot.check_guarded_query_constructor_copy` 从同一完整 AST fresh
执行 guard→query/minimum/quotient→构造字段链，再 fresh 检查全部显式引用。
逐一要求无 capture、同源同 record 的直接复制、相同字段完整双射、无地址发布、
独立完整目的对象及 trivial destructor，并消费顺序/cleanup 各子项。
普通函数与显式模板实例选点分开；后者必须经过原有 concrete-caller 检查。

结果仅在 `unexposed-fresh-automatic-object/v1` 模型内成立。旧栈指针、跨
activation 保留地址、伪造指针、栈探测、异步与非局部干扰没有由此验证。
其它实参、opaque calls 与 cleanup 不被宣称纯；所选复制不保证可达。
父报告只给选定复制若执行时的字段区间；runtime provenance、launch、source
program 与 deployable 仍 false。不是最终配置验收或新的 GPU 适配结果。

## 实际重放命令

```bash
mkdir -p artifacts/wb-hip-copy-model-20260930-02
PYTHONPATH=src python - <<'PY' > artifacts/wb-hip-copy-model-20260930-02/report.json
import json
from wavebridge.verification.field_snapshot import check_guarded_query_constructor_copy
p=json.load(open('artifacts/wb-hip-query-guard-candidate-20260930-01/native.json'))['payload']
r=json.load(open('artifacts/wb-hip-source-guard-20260930-01/report.json'))
abi={'int':{'bits':32,'signed':True},'unsigned int':{'bits':32,'signed':False}}
print(json.dumps(check_guarded_query_constructor_copy(p,'0x77692424bac0','0x77692424bda8',
 '0x77692424bfb8','0x77692424c3c0',r['selection'],r['conversion_contract_assumed'],
 r['output_contract_assumed'],abi,query_guard_id='0x77692424bc18',
 copy_expression_id='0x7769241d4cc8',instantiated_function_id='0x2d7f1410'),indent=2))
PY
```

旧报告仅供选点与外部协议，不消费旧通过状态。
输入 native SHA256：`df7d0b37e1d7ca16977f6d133285705d004a655e880b87b635148a373816e8b5`。
外部协议来源 SHA256：`771f1a83bcc2c30b524f38a4245034bae47cd6558db99f5becb72285d0dae378`。
冻结实现 SHA256：`fdfb48a842df01b8067df0e182c7b63304b87d065df283773c5e04adbc16c27e`。
01报告使用补充顶层模板实例选点hash之前的版本，保留但不替代02验收。

## 测试与审阅

新增真实源码测试涵盖两个 switch copy 正例、写字段、地址逃逸、显式析构、
汇编、capture、构造器 this 发布、复制构造器发布引用、错误选点和预算。
另有 opaque helper 使用保留指针的边界样例：条件模型可 checked，但必须
保留 runtime provenance=false，不能称为真实 C++ 别名证明。

首轮正例因普通函数误走模板实例门槛，以及 fixture tag/typedef 名称不同而
被原有受限复制器拒绝。分别显式区分普通/模板选点、调整 fixture 到支持子集，
没有放宽复制类型门槛。失败日志保留于 `/tmp/wb-copy-model-tests.log` 和
`/tmp/wb-copy-model-targeted.log`；修正后新增三项专项通过（26.391秒）。
Sol只读复核要求缩小“无别名”字段表述，已改为仅在受支持AST子集未观察到
地址发布，并收紧 invariant 基础范围；外部 provenance 假设没有被删除。
最终复核另要求顶层绑定 instantiated_function_id，已加入值与哈希，并补充
父子报告哈希一致性断言。Clang17专项28项147.621秒通过；补充绑定断言后
该专项中的对应测试单独重跑通过（6.331秒）。完整Clang23捕获兼容性缺口
未在本轮修复，不据此宣称所有工具链均支持。

## 冻结验收

- 最终 `make check`：1382项，259.326秒，全部通过，无跳过；日志
  `/tmp/wb-copy-model-check-final.log`。沿用固定工具链：native capture使用
  Clang17，其余visibility/unary/using-shadow/enum使用Clang23；插件位置
  `artifacts/toolchains/clang{17,23}-enum-20260930/`。
- 最后两处报告字段补充前的全测亦通过：1382项，261.214秒，日志
  `/tmp/wb-copy-model-check.log`；不以它替代冻结全测。
- `make demo` 与 `git diff --check`通过。
- 01重放为条件checked，22copy，字段32/4/1，deployable=false；SHA256
  `571ffdef8b46ef104f15598f748a467b8ad7f833ae78e16f02fac60cf8c36046`。
  该版本没有最终顶层模板实例hash，故不作为最终冻结工件。
- 最终02报告同样条件checked，完整22copy、所选block copy的三个字段区间
  为[32,32]/[4,4]/[1,1]；父子模板实例hash一致。报告SHA256：
  `1365905a0938b1749389d8d871637b0cbcae430a063cf6bbae405baaa5f6450c`。
  runtime_object_provenance_verified、launch_binding_checked、source_program_checked、
  deployable均false。完成后实现hash与上列冻结版本一致。
