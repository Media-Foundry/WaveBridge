# HIP threads 对象结构重放（2026-09-30）

基线f0ea3ac，wb03-source-ast。未改生产checker，没有GPU或新编译采集。
现有驱动HIP模式允许threads-object，但其变量选择从本次fresh checked
launch配置slot 1的直接CXXConstructExpr取得，而非填写CUDA对象ID。
严格接受单个直接DeclRef VarDecl和可选NoOp；复杂来源拒绝。
该选择只是要检查哪个对象，不证明这是值保持copy。

```bash
PYTHONPATH=src:. python3 -u -m experiments.softmax_launch_native \
  --profile hip --threads-object \
  --native artifacts/wb-hip-native-20260927-01/native.json \
  --output artifacts/wb-hip-threads-object-20260930-01/report.json
```

报告SHA `e65a7533f50e45828c786b502de082fd102528d18e25a4d35cb353a6efa3ee75`。
输入SHA仍为 `46ac52b1c672fadd0e5a66bb3ab380373e0cd69929713d96e7010f375a0cd63e`。
输入/src/driver前后稳定，结束后再次核对一致。大工件仅在本地artifacts。

## 实际结果

launch绑定仍checked，4槽位8形参；这不覆盖对象子检查。
slot 1构造 `0x745c579e4968` 引用变量 `0x745c57a5bfe8`，
唯一所在实例函数 `0x22508c60`。fresh对象检查unknown，原因
`fresh_conditional_object_initialization_not_checked`。

初始化构造 `0x745c57a5c138` 绑定constructor `0x2177f760`，
所属record `0x2177f198`。constructor-effects拒绝进入受支持子集：
`record_attribute_unsupported`。初始化实参warp_size和warps_per_block
不是const/constexpr，当前常量入口将其保留symbolic，不从变量名称或旧baseline填值。
另行只读核对同一record，其唯一直接属性为VisibilityAttr，implicit=true、
visibility=default（属性ID 0x2177f290）。这只是AST观察，尚未修改属性支持规则。

因此对象检查尚未到达显式引用/复制清单：空copy inventory不是“没有copy”。
也没有检查完观测调用、配置求值、对象生命周期/历史保持、配置值或lane域。
本轮不能声称观测函数无副作用；下一步应定位该record属性和host尺寸值链。
报告中launch与对象子状态必须分别阅读，顶层配置值/lane/source/deploy/GPU均false。

## 回归

5项driver编排fixture通过，包括精确变量改名、unknown/重复slot、BitCast/调用来源
拒绝，以及以fresh slot和精确owner重做对象检查、unknown不升级。
这些mock不是源码保证；真实HIP重放另行运行现有生产checker。
Sol只读复核无阻断；指出后续若建立copy inventory，需精确核对slot构造也在其中，
不能拿同变量的其它copy通过替代选定slot的检查。
最终make check：1277项、97.147秒、无跳过，日志 `/tmp/wb-hip-object-check.log`；
SDK23/AOCC17各自匹配插件的混合验收，非全量SDK23。make demo和diff检查通过。
