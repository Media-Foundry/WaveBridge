# HIP exp/log 调用与重复声明取证

2026-09-27，基线`15155fe`。本轮不修改生产checker，不新增效果假设，不执行GPU。

## 可重放命令与工件

```bash
PYTHONPATH=src:. python3 -u -m experiments.softmax_call_audit \
  --native artifacts/wb-hip-native-20260927-01/native.json \
  --output-dir artifacts/wb-hip-math-audit-20260927-02
```

输入SHA256：`46ac52b1c672fadd0e5a66bb3ab380373e0cd69929713d96e7010f375a0cd63e`。
报告`report.json` SHA256：
`74e6956f0d75e3732a7ab86586505e1a1477fff6c6abed0238053f4059771ea0`。
命令退出0，状态observed，输入、src实现和记录的实验辅助模块哈希前后一致。
这仍不是SDK、所有Python依赖或构建输入的完整闭包保证。

历史`artifacts/wb-hip-math-audit-20260927-01/report.json`保留，SHA256
`d52087e1940fde6291f06bf108762641d5c53de001a025595c8cdb48c89a2570`。
初版没有展开不一致声明的独立观测，因此math列表为空；不能解读成没有数学
builtin调用。第二版保留这些原始声明的每次出现，不将它们任选一份接成可信路径。

## 观察结果

诊断调用图有32个节点、41条边，待遍历队列为空；只是所支持语法的直接引用
清单，不是动态可达性、完整调用图或执行覆盖。模板分支未用于筛除该清单，
其中log等调用不意味着当前非log-softmax实例必然执行它。

| 声明 | 精确ID | 出现次数 | 两次原始声明比较 |
| --- | --- | --- | --- |
| exp | `0x2054bf90` | 2 | 全部字段相同 |
| log | `0x2054eb08` | 2 | 全部字段相同 |
| expf | `0x204e0d90` | 2 | 仅`loc.file`显式出现与否不同 |
| logf | `0x204e70d8` | 2 | 仅`loc.file`显式出现与否不同 |

exp/log既出现在TU中，也被std的UsingShadowDecl再次列出。诊断清单仅在显式
opt-in且整个声明相等时遍历一次，保留重复次数；默认行为不变。
expf/logf的两次出现不满足严格相等，图遍历停下；报告另保存8份完整声明及
父路径，各自观察内部调用。这不等于解析了冲突，更没有修改传入checker的AST。

源码/原始AST可观察到`exp → expf → __builtin_expf`和
`log → logf → __builtin_logf`。SDK的`__clang_hip_math.h`分别在430–431、
533–534行定义后两个wrapper；前者直接调用builtin，后者经过FAST_OR_SLOW
宏，本次AST选择builtin。不能由这次宏展开推广到其他编译选项。

| native名称 | call ID | callee ID | builtin ID | 原checker结果 |
| --- | --- | --- | --- | --- |
| `__builtin_expf` | `0x204e0f28` | `0x1ff1d600` | 536 | unknown / builtin_structure_not_supported |
| `__builtin_logf` | `0x204e7270` | `0x1ff25bf0` | 932 | unknown / builtin_structure_not_supported |

报告保留两个完整native观测及fresh结构检查结果。已有builtin入口只支持
huge_valf/nanf受限形状；不能把一元浮点调用当成零参或字符串参数调用放行。
原scalar-forwarding入口还要求声明/表达式身份唯一且使用普通函数decay，
不能直接把这条builtin路径当作旧CUDA外部标量leaf路径。

## 下一门槛

1. 用真实Clang最小using引用及冲突负例，确定重复声明的前端表示边界；
   不能仅删除所有重复ID，或忽略任意不一致字段。
2. 独立检查一元float builtin身份与实参求值，包括带写入实参的拒绝；
   结构支持不等于builtin无写入、正常返回或数值语义已证明。
3. 然后才考虑将明确效果协议接入真实循环；保留源有效性、完整迭代域和
   输出数值契约，不用本次诊断结果签发整核/部署许可。

## 验证

新增测试是明确标注的诊断/编排fixture，检查完全相同重复的opt-in、元数据
冲突不遍历、错误输入哈希拒绝，以及不一致声明保留而不声称路径成立。
最终1223项CPU测试通过（96.221秒），匹配AOCC原生插件启用，无跳过；
make demo与diff检查通过。日志为`/tmp/wb-hip-math-final-check.log`和
`/tmp/wb-hip-math-demo.log`。完成后再次复核报告中的driver依赖与src哈希，
仍与当前文件一致。本轮未运行GPU或核验远端CI。
