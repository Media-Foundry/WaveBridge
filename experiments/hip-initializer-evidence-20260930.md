# HIP local_idx 初始化诊断（2026-09-30）

基线 `7d2f63c`，分支 `wb03-source-ast`。本轮没有修改生产checker或运行GPU。
驱动 `experiments/hip_initializer_diagnostic.py` 固定既有HIP native工件SHA
`46ac52b1c672fadd0e5a66bb3ab380373e0cd69929713d96e7010f375a0cd63e`
与 local_idx 声明 `0x745c579bb0c0`，不消费旧成功报告。

## 命令与结果

```bash
PYTHONPATH=src:. python3 -u -m experiments.hip_initializer_diagnostic \
  --native artifacts/wb-hip-native-20260927-01/native.json \
  --output artifacts/wb-hip-initializer-diagnostic-20260930-03/report.json
```

最终报告SHA：`7835465dff713c229c9188fccbcc71e00a9242b61c8a6b7cffa19ac00a7a1c29`。
前后源码/driver/输入哈希稳定，结束后再次核对一致。
顶层 `observed` 仅描述稳定采集，不是检查通过。

源码initializer link恢复到getter `0x2202d268`；诊断选点依次发现
`0x2202aab0`、外部声明 `0x2202a958`（`__ockl_get_local_id`）。
`observed_path`只是每层唯一call的候选路径，不能独立证明返回数据流。
最终fresh `check_source`重做initializer/getter/conversion，不信任此路径签发结论。
外部调用返回AST类型为size_t，desugaredQualType为unsigned long。
ABI显式假设int32、unsigned int32、unsigned long64，不是本轮测量。

仅给出完整返回类型域 `[0,18446744073709551615]`，不提供lane小域。
getter fresh检查确认实参0的int→unsigned int转换checked；返回中的
unsigned long→unsigned int转换rejected，原因
`return_conversion_not_value_preserving`。父初始化检查相应rejected，原因
`initializer_getter_not_checked`；尚未检查到最终unsigned int→int初始化转换。
这不说明真实硬件会返回该反例，也不说明原始HIP kernel错误。
它说明仅靠完整类型范围不能建立值保持，仍需实际launch与外部坐标范围依据。

## 保留的未成功尝试

- 01：仅支持native leaf选点，遇到外部声明无body停止；SHA
  `838eda9574a2144401c684fc3b3a9e0a48d4cb554b3bb482a57e245e34df1414`。
- 02：选点支持external leaf，但驱动把return_type传成字符串而非类型证据对象，
  getter为unknown/type_evidence_missing；SHA
  `7e25634bf6cd3dd706d93b11b6c4d47ff932c2748d1f26991ef6bb53be2bd0c6`。
- 修复驱动协议后fresh执行03；未改写旧报告，也未修改checker以放行。

## 验证与范围

4项driver单元测试通过，覆盖固定哈希、完整类型域、external literal、
非literal/不支持cast拒绝及fresh子状态传播；这些是mock编排fixture，
不是源码语义或真实Clang测试。上面的既有真实HIP AST重放不mock checker。
CPU回归使用SDK23与AOCC17各自匹配插件的混合环境，不称全量Clang23验证。
冻结最终代码后的 `make check` 为1272项、97.422秒、无跳过，日志
`/tmp/wb-hip-initializer-closed-check.log`。驱动定向4项通过，日志
`/tmp/wb-hip-initializer-final-driver.log`。
`make demo`、`git diff --check`通过。Sol只读复核无阻断，提醒候选路径非证明。

lane范围、外部API语义、值历史、完整迭代域、整核与部署标志始终未建立。
所有原始大工件保存在本地artifacts，不声称随Git发布完整复现包。
下一步：绑定实际launch和外部坐标协议，然后fresh检查初始化与循环前历史，
不能因为历史baseline使用block.x=32就直接赋予当前leaf `[0,31]`。
