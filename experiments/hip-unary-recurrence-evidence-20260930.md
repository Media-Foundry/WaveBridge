# HIP 普通计算循环的条件递推重放

基线`e360716`，2026-09-30。只扩展开发重放驱动，没有修改生产checker。
目标是核实一元调用效果接通后，真实计算循环的递推是否可以恢复；不是
GPU、浮点等价或整个softmax通过声明。

## 命令与范围

```bash
PYTHONPATH=src:. python3 -u -m experiments.softmax_unary_work \
  --native artifacts/wb-hip-native-20260927-01/native.json \
  --math-protocols artifacts/wb-hip-native-effect-20260930-01/report.json \
  --zero-protocols artifacts/wb-hip-native-20260927-01/conditional-work.json \
  --recurrence --output artifacts/wb-hip-unary-recurrence-20260930-02/report.json
```

三份输入SHA分别为：

- `46ac52b1c672fadd0e5a66bb3ab380373e0cd69929713d96e7010f375a0cd63e`
- `a8af8a027126343d9221d593efdd2a1e709b1ba1588d89ee129fcf21fa9f617b`
- `7952d53d103ccbf4c130fc4c775a67b726a039b4c652eddc4b270dc42939de87`

同一selected entry `0x745c579e5490`，两个模式使用完全相同的8条协议，只
改变一元/using开关。旧报告只提供未验证协议字典，不消费成功结论；新
recover_with_call_effects从原native AST fresh运行。int32是外部ABI前提。
不是仅选择成功循环，也不删除未消费协议来追求顶层通过。

## 首轮诊断记录与报告修正

首轮`artifacts/wb-hip-unary-recurrence-20260930-01/report.json`完整保留，
SHA256 `be015dc64cf234e13f6d98e6db14c8bcde11d1771e2251f52f7536eb2bdd0857`。
其实际fresh检查是整entry递推，但外层schema/selection仍沿用guarded-work
文字。GPT-5.6 Sol指出此报告描述错误；不能把空`checks`解读成无目标。

修正后使用独立`softmax-unary-entry-recurrence/v1`和`mode=entry_recurrence`，
selection明确整entry、无guarded预选；`checks`与`recurrence_checks`分别
限定为guarded与recurrence结果。旧工件不改写，最终证据来自02重跑。

首轮观察到：源码第149/152行的计算循环，由默认call_effect_not_checked
转为条件recovered，起点0、步长1、bound常量分别2和4。它们是嵌套语法循环，
不是两个独立kernel。默认4 recovered/4 unknown，启用6 recovered/2 unknown。
第192/197行的guarded输出循环仍unsupported_control_flow_in_body，整entry
unknown，log协议未消费。上一轮独立guarded-work成功不能直接填进递推报告。

## 未建立的性质

恢复报告仍明确源有效性、存储不别名、完整迭代域、signed overflow与外部
调用效果的前提；无输出值、FP环境、机器码、跨波宽等价或部署结论。
八个循环只是同一实例的语法节点，6/8不能作为真实语料接受率或论文覆盖率。
导入辅助脚本没有单独运行前后hash，不声称完整Python依赖闭包。

## 最终验收

02进程退出0，observed。输入/src实现/driver自身hash前后一致，结束后再次
与当前文件核对一致。报告SHA256：
`2f1faad5825c63716b51abad55d06621b00602c0cf66b78ba605a1455672e3f7`。
两模式的完整`recurrence_checks`与01完全相同，报告外层已正确标记模式。

| 源码行 | 默认模式 | 一元/using启用 |
| --- | --- | --- |
| 103、105、118、123 | recovered | recovered |
| 149、152 | unknown：call_effect_not_checked | recovered，外部效果前提下 |
| 192、197 | unknown：unsupported_control_flow_in_body | unknown：同左 |

两个模式整体均unknown/one_or_more_loops_unknown。默认未消费后3处exp与log
协议；启用后只剩log未消费。未删除这些协议或替换未知循环。

1265项CPU测试通过（106.376秒，无跳过），make demo/diff通过；4项driver
fixture0.004秒通过，验证模式严格布尔、输入hash、协议冲突和不消费旧成功
结果。全量采用匹配SDK23/AOCC17混合插件配置，不称全量SDK23或远端CI通过。
日志`/tmp/wb-unary-recurrence-{check,demo,driver}.log`。未执行GPU。
Sol二次只读复核确认报告模式问题已解决，无阻断项。
