# HIP minimum 操作数来源（2026-09-30）

基线e3e9440，分支wb03-source-ast。扩展既有host-dimensions报告，不修改生产checker。
仅在fresh minimum检查成功后，按其operand_declaration_ids重新绑定唯一同owner
VarDecl，保存原声明与初始化树、fresh执行现有常量求值。直接调用再交给既有
observe_call核对精确调用/声明/initializer身份，不按函数名建立语义。
只使用softmax_host_api_evidence的纯观察函数，没有调用其联网run；模块hash已绑定。

```bash
PYTHONPATH=src:. python3 -u -m experiments.softmax_launch_native \
  --profile hip --host-dimensions \
  --native artifacts/wb-hip-native-20260927-01/native.json \
  --output artifacts/wb-hip-host-origins-20260930-01/report.json
```

输入SHA `46ac52b1c672fadd0e5a66bb3ab380373e0cd69929713d96e7010f375a0cd63e`；
报告SHA `9df22e0d8cc0e8997f6ca7c371f690b3cdee0575b0e19991a0f78535c3175710`。
输入/src/driver依赖前后稳定且结束后复核一致。工件仅在本地artifacts。

## 实际来源与结论

1. next_power_of_two声明0x745c57a5b680是const int，其initializer为
   `1 << log2_elements`，读取0x745c57a5b580。常量求值在这条可变依赖上
   返回unknown/variable_not_constexpr_or_const，不代表该const声明本身不是const。
2. warp_size声明0x745c57a5b7a0调用0x22041db8；精确调用观察为observed，
   同symbol定义只有该声明。其源码并非literal-return helper：调用hipGetDevice
   和hipGetDeviceProperties，读取properties.warpSize，写入wb_api_width并递增
   wb_api_calls，最后返回全局wb_api_width（0x22041670）。这是源码观察，
   不是自动API语义/效果证明。可变warp_size不能由常量求值建立域。

原minimum/历史/商/商历史四项仍条件checked；它们没有验证上面的初始化域。
每个来源明确保持runtime_return_interval=null、initial_value_preserved_to_update=false、
api_effects_established=false。不能从定义存在、名称warp_size或W7900历史运行
推出本次源码的完整返回域，更不能把有观测写入的helper记为纯函数。

下一步分开处理：输入相关log2/移位的合法域及到minimum的保持；精确设备查询
API协议、字段读取和全局观测状态的值流。不要为通过而把原helper改成return 32。
无GPU、新编译、网络下载、性能或部署作业。

## 回归

6项driver测试通过，其中新增对fresh常量求值/API观察参数、原AST保留、
unknown与未建立标记不升级的断言。属于mock编排fixture；真实HIP报告另行
调用实际checker。Sol只读复核无阻断。
最终make check：1280项、98.018秒、无跳过，日志 `/tmp/wb-host-origins-check.log`。
使用SDK23/AOCC17匹配插件混合验收，非全量SDK23。make demo及diff检查通过。
