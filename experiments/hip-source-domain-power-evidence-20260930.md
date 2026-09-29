# 从源码守卫域到幂次初始化

基线`982f788`，分支`wb03-source-ast`。无GPU执行。

## 新组合入口

`power_ceiling.check_guarded_shift`不接受数值域或外部成功报告：

1. 从同一完整AST fresh检查精确caller、const局部量、guard、call及实参位置。
2. 取得源码推导的离散集合，以及实际callee对应的形参ID。
3. 对集合中每个值，以单点入口域fresh执行entry-to-shift检查，核对入口保持、
   直接读取、helper循环和紧邻移位。
4. 核对同根哈希，所有分支通过且结果为单点，才合并结果集合。

这是一项有限集合分情况推导，不以区间包络填补未检查值，也不运行随机输入。
入口数值前提由同次guard检查解除；源有效、普通顺序/无非局部跳转、对象存活
不替换、实际调用实现与AST一致等前提仍保留。最多64个离散值，超限unknown。

结论只属于选定调用的callee invocation及其首次幂次初始化，不是所有调用者
的通用输入协议。不证明该调用必然执行、其它实参安全、后续值保持或GPU行为。
嵌套子报告保留其局部单点前提；顶层discharged_obligations明确说明哪些前提
由本次源码集合分情况提供，不能孤立地拿子报告宣称运行时输入已经验证。

## 无手填域重放

```bash
PYTHONPATH=src:. python3 -m experiments.softmax_launch_native \
  --profile hip \
  --native artifacts/wb-hip-native-20260927-01/native.json \
  --output artifacts/wb-hip-source-domain-power-20260930-01/report.json \
  --host-dimensions
```

固定输入SHA256：`46ac52b1c672fadd0e5a66bb3ab380373e0cd69929713d96e7010f375a0cd63e`。
没有`--power-input-domain`；旧区间诊断字段为null而不是伪造成功。
旧entry_domain_policy文本仅描述可选legacy模式，不表示本次提供了该前提；
实际是否执行由四个legacy子检查字段的null状态确认。
driver仍保留每个候选guard及unknown记录，组合入口自行重新检查，不消费并列
guard报告的status。外层配置、lane、source_program_checked、deployable仍false。

## 回归

新增真实Clang组合正例与拒绝例：源码集合{65,128}→结果{128}；
guard允许0时即使guard本身checked，helper域不能支持，组合必须unknown；
指数/结果声明交换也拒绝。与既有逃逸、绕过、其它实参及身份测试一起运行。
定向5项真实Clang和6项driver测试通过（driver fixture不是实际源码重放证据）。

下一步处理初始化结果及设备API宽度到minimum更新点的历史；不能把此局部
结果直接称为最终block配置或自动GPU适配成功。

## 实际结果

报告SHA256：`81ba956e9aa1d5f2eb10528044489154975b60afafcde816ebd283e50113c4a5`。
`inputs_unchanged=true`。精确guard `0x22494e28`的组合checked，entry_values
为[65,128]、result_values为[128]；没有输入数值域参数。其它5个guard组合
保持unknown。4个旧区间诊断子报告均为null，确认新路径没有使用legacy前提。

完整make check为1307项、98.593秒、无跳过；日志
`/tmp/wb-source-domain-power-check.log`。沿用SDK23 visibility/unary/using和
AOCC17 native插件组合；定向5项真实Clang、6项driver测试、demo/diff通过。
Sol只读复核无阻断。源码与驱动在真实重放期间冻结，无GPU执行。
