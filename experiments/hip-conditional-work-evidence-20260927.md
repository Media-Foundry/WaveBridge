# 实际 HIP 源码的条件循环保持性重放

2026-09-27，基线`86c8435`。复用既有softmax_builtin_effects driver及生产
checker，不新增kernel模板，不修改源码或放宽checker。

## 冻结输入与对照

```bash
PYTHONPATH=src:. python3 -u -m experiments.softmax_builtin_effects \
  --native artifacts/wb-hip-native-20260927-01/native.json \
  --profile hip-gfx1100 --guarded-work \
  --output artifacts/wb-hip-native-20260927-01/conditional-work.json
```

HIP profile固定native工件SHA256
`46ac52b1c672fadd0e5a66bb3ab380373e0cd69929713d96e7010f375a0cd63e`。
原CUDA默认profile保持原有独立hash约束，不能将CUDA报告传入HIP模式。

选择器沿精确callee和单return函数体自动选择huge_valf/nanf路径；不填写
循环关系，不提供checker成功结论。协议显式假设精确leaf实现无内存写入、
调用有效且正常返回，evidence_reference仍标记为未验证开发敏感性假设。
先前HIP lowering探针可以帮助解释该假设，但本实验不把它认证为生产语义。

首先分别执行默认恢复和条件恢复；随后从同一原始实例选择含BreakStmt的
ForStmt，每个循环分别fresh运行无leaf假设和带该循环精确调用协议两种模式。
两个模式均启用已有静态分支与受限嵌套检查。输出保存完整子报告和剩余前提，
不是只记录通过数量；嵌套节点不被计为多个独立kernel。

## 实际结果

命令退出码0，报告为`artifacts/wb-hip-native-20260927-01/conditional-work.json`，
SHA256为`7952d53d103ccbf4c130fc4c775a67b726a039b4c652eddc4b270dc42939de87`。
输入与实现前后哈希一致，完成后再次核对当前driver和src哈希一致。
这不是全部构建输入闭包证明：导入的实验选择器辅助模块未纳入driver自哈希。

默认恢复1个recovered、7个unknown；加入3条精确leaf协议后为4个recovered、
4个unknown，总状态仍unknown。剩余两处调用效果未知、两处控制流不受通用
恢复器支持，不能用下面的独立局部检查覆盖这些unknown。

| 原始循环节点 | 源码行 | 无leaf假设 | 带精确leaf假设 |
| --- | --- | --- | --- |
| `0x745c579c4018`，外层输出循环 | 192 | unknown / call_effect_not_checked | checked |
| `0x745c579c3fa0`，内层输出循环 | 197 | unknown / call_effect_not_checked | checked |

两个检查均只消费`0x745c579c3aa8`调用协议，绑定native leaf
`0x20334a68`（`__builtin_nanf`）。两者均报告
`work_preserves_protected=conditional`、`full_iteration_domain_established=False`、
`external_call_effects_verified=False`；不是两个独立kernel的成功适配。

## 保证边界

即使guarded-work checked，也只是在完整列出前提下保持受保护依赖存储。
整数ABI int32、源程序有效性、存储不别名、外部leaf效果与正常返回等条件
仍需区分；不由该结果推导完整迭代域、输出覆盖、IEEE浮点等价或部署许可。
不将源码结构分析、条件语义检查和18项历史数值测试合并成一个普遍正确性声明。

## 回归

GPT-5.6 Sol新增4项明确标注mock的driver测试，覆盖选项类型、跨profile
错绑、默认模式隔离及循环协议筛选；它们不作为真实Clang或GPU证据。
完整1219项CPU测试通过（93.242秒，匹配AOCC原生插件启用、无跳过），
make demo通过。日志为/tmp/wb-hip-conditional-check.log与
/tmp/wb-hip-conditional-demo.log；本轮未执行GPU或核验远端CI。
