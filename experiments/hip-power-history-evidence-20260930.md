# 源码派生 power 到 minimum 语句入口的保持

基线`3f38885`，分支`wb03-source-ast`。无GPU执行。

## 边界

既有minimum历史检查对中间语句做严格副作用检查，不能将设备API调用自动
当作纯函数。本轮增加私有、显式opt-in的const-local模式，不改变旧默认模式。
只有已fresh建立初始化关系的普通自动`const int`允许进入；再独立核对声明/
函数/同块语句顺序，复用全函数引用用途闭合，拒绝写入、地址/引用逃逸及不支持
控制流。结论依赖有效C++执行、对象生命周期不替换、正常前进至目标语句、无
非局部跳转/栈内省/异步干扰。

中间API可能读写其它存储，甚至无法正常返回。因此其statement_checks记为
not_evaluated，intervening_effects_checked=false，不签发其无副作用结论。
若正常到达目标语句首次入口，则所选const对象仍保持初始化值；目标本身未求值。

`check_guarded_shift(..., target_statement_id=...)`只用同次源码域/初始化检查
结果构造内部seed，不接收调用者自填成功报告。history失败时整体unknown；
已成立的初始化子证据保留，但不能据此宣称到目标的历史也成立。
组合入口沿用原schema并以scope/history_check/value_preserved_to_target_entry
区分保证；消费者不能只检查schema或初始化result_values就接受历史结论。

## 重放

```bash
PYTHONPATH=src:. python3 -m experiments.softmax_launch_native \
  --profile hip \
  --native artifacts/wb-hip-native-20260927-01/native.json \
  --output artifacts/wb-hip-power-history-20260930-02/report.json \
  --host-dimensions
```

输入SHA256：`46ac52b1c672fadd0e5a66bb3ab380373e0cd69929713d96e7010f375a0cd63e`。
driver从fresh minimum检查取得assignment ID，作为power历史终点；没有手填
数值域，没有把历史W7900的API宽度32作为静态前提。

首轮01报告保留，SHA256
`27bf5dbbb9c3276fc53d6cc6191104c71ec61f100968f322655ef4be98c73497`。
其初始化仍{128}，但history为unknown/updated_local_storage_escape_or_other_write，
不是历史通过。进一步真实AST定位到ref`0x745c57a5b930`：它是minimum条件左值
的一个分支，整个const-int lvalue条件表达式随后才被LValueToRValue读取。

仅新const模式增加这种wrapper：当前引用须为条件的值分支，条件为bool，两个
分支与parent同型且均lvalue，整条用途链最终仍须普通取值。条件左值再取地址
的真实Clang负例仍拒绝。默认旧历史模式不放宽。02使用修正后的冻结实现。

## 回归

7项真实Clang定向测试通过。新增中间opaque调用的const正例，以及power取址
逃逸、mutable power、跨函数目标负例；正例仍明确target_statement_checked=false。
旧minimum/quotient默认历史模式不变。首轮完整1309项CPU测试99.101秒通过，
日志`/tmp/wb-power-history-check.log`，但没有抓到真实HIP条件左值支持缺口。
最终版本重新完整验收1309项、98.331秒通过、无跳过，日志
`/tmp/wb-power-history-final-check.log`；沿用SDK23 visibility/unary/using及AOCC17
native插件组合。定向7项、demo/diff通过，Sol两轮只读复核均无阻断。

后续仍须建立设备API返回域、另一个minimum操作数及目标表达式关系的数值
组合；不能从power保持到入口直接推出block尺寸或设备坐标范围。

## 最终真实结果

02报告SHA256：`9ef2e5866d91211829338342e0457c9797aa3573058f17c9d670d09374705982`。
输入/实现哈希稳定。源码派生{128}保持到minimum assignment
`0x745c57a5b9d0`首次入口，组合及history均checked，value_preserved_to_target_entry=true。
中间设备API初始化声明`0x745c57a5b848`仍not_evaluated，
intervening_effects_checked=false，target_statement_checked=false。
因此它不是minimum数值结果、API宽度或完整host配置通过。首轮01历史unknown
继续保留，不能因顶层launch binding checked而误读成历史也通过。
