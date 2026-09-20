# launch 前置守卫交接

- 日期、分支和基线：2026-09-20，`wb03-source-ast`，`9be7ef1`。
- 用户约定：中文；直接本地 commit，不开 PR；本轮不推送。
- 已完成：Sol 子代理实现 `analysis/launch_guards.py` 与结构负例；主代理
  审查、集成源码入口、补真实 Clang CUDA fixture 与声明 ID 关联验收。
- 目标：从源码恢复到达 launch 的必要整数区间，不按变量名或人工关系 oracle
  填值。连接 grid 实参与 kernel 列数实参引用的精确 host 变量声明。
- 验证命令与结果：见最终验收记录。
- 未执行：新 GPU 运行、MI250/native64、性能、自动候选或共同工具能力实验。
- 范围：源有效性、ABI 及运行语义仍需单独建立；守卫必要条件不等于合法输入
  协议，也不证明 host 可达性。`checked=false`、`deployable=false`。
- 本地工件仍被忽略，不是公开复现包。所有修改与本交接一起直接提交。
- 下一项：在独立检查器中连接显式区间与构造参数转换，而不把 symbolic 改名
  为常量；继续验证线程坐标、shared容量及源/目标关系。

## 最终验收记录

主代理执行 `make check`：227 项通过；真实 Clang CUDA fixture（不运行 GPU）
覆盖直接 launch、宏式包装、普通 host 错误检查，以及地址逃逸/跳转拒绝。
单元测试对4种比较符和左右交换按小位宽枚举补集核验。

```bash
PYTHONPATH=src python3 -m wavebridge.source \
  benchmarks/cases/llama-rmsnorm/baseline/rmsnorm_logical32.hip.cpp \
  --compiler /home/husrcf/Code/ProtBind/wavebridge/artifacts/toolchains/sdk-view-sx4rmd37/bin/hipcc \
  --compiler-arg=--cuda-device-only --symbol rms_norm_f32_logical32 --int-bits 32 \
  --output-dir artifacts/wb03-source-launch-guards-01
```

退出0，`status=analyzed`。新报告 `host_guard_intervals.status=recovered`，
grid 首实参的声明 ID 对应 `[1,8]`，列数 kernel 形参的 host 实参 ID 对应
`[1,1023]`；5项无关 guard 保存为 skipped。主代理对两个关联执行断言，并
核对报告内全部实现哈希、源码哈希和 AST 文件哈希一致。未改基线源码。

```bash
PYTHONPATH=src python3 -m wavebridge.configuration_check \
  artifacts/wb03-source-launch-guards-01/report.json \
  --abi examples/abi/int32-conditional.json \
  --output artifacts/wb03-source-launch-guards-01/configuration-model-check.json
```

退出2，整体仍unknown；新增源码必要区间没有被当作常量或部署许可。
`git diff --check` 通过；没有新 GPU 执行、推送或 PR 操作。
