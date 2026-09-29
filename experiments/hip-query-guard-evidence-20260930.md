# 查询返回值到错误包装参数的组合

基线 `9f6dbb4`，分支 `wb03-source-ast`。本轮无 GPU 执行。

上一轮只独立检查了包装定义，没有把实际查询返回值与该定义中的参数连接。
新增同模块 `normal_return_guard.check_call(root, call_id)`，不接受旧检查报告、
手填成功状态或 API 名字。它从完整 AST 重新绑定直接外层调用及内层调用：

- 外层是唯一 void 调用，精确引用含一个按值参数的包装定义；
- 唯一实参本身是直接调用产生的 prvalue，类型字典与包装参数完全相同；
- 不剥离实参上的 cast、comma、conditional、load 等表达式；
- fresh 检查包装正常返回守卫，核对同一参数身份后组合结论。

结论是：**若所选包装调用正常返回，则该次内层调用返回值按守卫中的转换
进行比较时与常量匹配。**这不是重新执行查询，也不逆推原枚举值相等。
“query”只表示包装的直接内层调用；API 身份/实现不能由此名称或位置推断。
若传入另一个 helper 调用的结果，报告绑定的是那个 helper，而不是它的实参。

报告同时记录 query 声明、实参位置、对应形参及原始表达式。它不检查这些
实参的地址/输入有效性，不证明 query 写入对象、不证明 API 成功，也不证明
调用确实正常返回。运行时实际执行所选包装定义、noreturn 声明契约被遵守、
有效普通顺序执行且无异步/非局部干扰仍是显式前提。

driver 的 `query_result_check` 保存 fresh 组合，原 `wrapper_check` 来自同次
组合内的 fresh 子检查；不是独立旧成功报告拼接。报告哈希新增选择和身份策略。

## 命令

```bash
PYTHONPATH=src:. python -m experiments.softmax_launch_native \
  --profile hip --native artifacts/wb-hip-native-20260927-01/native.json \
  --output artifacts/wb-hip-query-guard-20260930-01/report.json \
  --host-dimensions
PYTHONPATH=src python -m unittest discover -s tests -p test_normal_return_guard_clang.py -v
```

输入固定 SHA256：
`46ac52b1c672fadd0e5a66bb3ab380373e0cd69929713d96e7010f375a0cd63e`。
定向真实 Clang 6 项已通过，覆盖不同 query 声明、常量替换、丢弃返回值、
算术后转换、条件选择、函数指针调用、未保护包装、身份冲突、预算和输入不变。
GPT-5.6 Sol 只读复核未发现阻断性问题。完整回归及真实结果见验收补记。

## 下一条外部义务

本机冻结 SDK 的 `hip_runtime_api.h` 第 2418–2432 行描述线程默认设备查询，
2513–2526 行描述属性输出，103 行将 warpSize 标记为 warp size。
这些声明/注释可用于明确外部契约的对象和参数，但不是对应运行库实现的证明，
更不能推出所选设备必然返回 32。后续应把精确输出对象、设备 ID、枚举转换
与冻结的 API/ABI 协议连接，不扩大本轮 checked 的范围。

所读本地头文件 SHA256：
`eedd1d07748a1fce0bea08c1f3c41ce8150b1c7c5cc7058e6605d178aa5773e7`。

## 验收补记

完整 `make check`：1318 项、99.534 秒、无跳过，日志
`/tmp/wb-query-guard-check.log`。工具链环境沿用上一轮：SDK Clang 23 负责
visibility/unary builtin/using-shadow，旧 native capture 使用 AOCC Clang 17
与匹配插件，普通 fixture 为 PATH clang++。`make demo`、`git diff --check`
通过。GPU 没有运行。

真实重放完成，inputs_unchanged=true。报告 SHA256：
`4daf978256ecf72e1a1c329dba9ffb86b501af6c52cb4f4855dad3609cb956f8`。
两份 query_result_check 均 checked，均明确绑定形参 `0x22040750`：

| 包装调用 | query 调用 | query 声明 | query 实参表达式 |
| --- | --- | --- | --- |
| `0x220430c8` | `0x22043000` | `0x217b5820` | `0x22042fb0` |
| `0x22043958` | `0x220432d8` | `0x217b69b8` | `0x220431a8`, `0x22043310` |

两者 query_result_preserved_to_parameter=true，API_success_verified、
call_normal_return_proved 仍 false。表中第二条的实参地址和设备读取表达式已
记录，但尚未与 field_snapshot 的对象身份及外部输出效果协议组成保证。
