# 设备属性 helper 的字段快照返回关系

基线`d93182f`，分支`wb03-source-ast`。无GPU执行。

## 为什么不能把 warp_size 当常量 helper

实际手工compat helper先构造properties、调用设备查询和检查包装，再执行：

```cpp
wb_api_width = properties.warpSize;
++wb_api_calls;
return wb_api_width;
```

历史W7900面板观察到32，不代表上述调用的普遍返回域已经建立。本轮只核对
“字段值在赋值处被读取，经不同全局计数器的递增后，按值返回同一快照”这一
局部关系。它能固定下一步API协议应该绑定的字段读取和对象身份，而不猜域。

`verification/field_snapshot.check`使用精确AST身份与类型，不按名称识别API。
尾部必须严格为赋值、不同普通全局int递增、同一全局int的普通读取返回；字段
必须是直接自动对象的plain-int成员，拒绝指针成员访问、volatile/bitfield等
不支持形态。计数器和快照真实存储互异仍是明确前提，不宣称解决链接别名。

## 条件与未建立的义务

检查以执行到达该suffix且正常返回、字段可合法读取、计数器递增定义良好、
普通顺序/无异步或非局部干扰为前提。源码前缀的API调用、成功状态、设备选择、
properties初始化及数值范围均未检查。`field_numeric_domain=null`，
`API_success_verified/field_value_initialized/prefix_effects_checked=false`。
它不是完整helper正确性、全局无副作用、API purity或运行库实现证明。

## 重放

```bash
PYTHONPATH=src:. python3 -m experiments.softmax_launch_native \
  --profile hip \
  --native artifacts/wb-hip-native-20260927-01/native.json \
  --output artifacts/wb-hip-api-snapshot-20260930-01/report.json \
  --host-dimensions
```

输入SHA256：`46ac52b1c672fadd0e5a66bb3ab380373e0cd69929713d96e7010f375a0cd63e`。
driver在已有精确零参调用绑定之后fresh执行suffix检查；不把结果自动写成
warp_size的数值域，也不改最低层source_program_checked/deployable标记。

## 测试范围

3项真实Clang测试覆盖合法快照、计数器覆盖快照、返回其它变量、中间调用、
volatile字段、字段值加一、重复身份、预算与输入不修改。6项driver fixture
通过，但fixture不是实际HIP工件证据。完整回归和真实结果在最终补记。

下一步需要针对已绑定对象/字段建立查询成功与外部API语义协议，再与返回
关系连接；不能把本轮条件checked改写成“wave32已静态证明”。

## 实际验收

报告SHA256：`68e8852fe85295781df8bfdc79ac62120094049a5649d943728477d994a4a961`。
inputs_unchanged=true。helper `0x22041db8`的suffix checked，绑定：
object `0x22041e90`、field `0x21318820`、读取`0x220439f8`、赋值
`0x22043a10`、snapshot `0x22041670`、counter `0x22041870`。
3条前缀语句仍未检查，字段域null，API成功/初始化/整核/部署仍false。

完整1312项CPU测试99.757秒通过、无跳过，日志`/tmp/wb-api-snapshot-check.log`。
沿用SDK23 visibility/unary/using和AOCC17 native插件组合；定向3项真实Clang、
6项driver、demo/diff通过，Sol只读复核无阻断。无GPU，未新增性能/数值实验。
