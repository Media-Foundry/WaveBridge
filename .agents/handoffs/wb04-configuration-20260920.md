# 条件配置字段检查交接

- 日期、分支和基线：2026-09-20，`wb03-source-ast`，基线 `c216f47`。
- 用户约定：中文回复；直接本地 commit，不创建 PR；本轮不推送或合并。
- 已完成：Sol 子代理实现 `verification/constructor_values.py` 及负例；主代理
  审查输入门控、集成 `configuration_check.py`、外部 ABI 示例、CLI 测试与协议。
- 检查范围：精确构造声明、参数位置、完整字段映射、由内到外整数转换和值保持。
  空映射、缺配置、symbolic、不支持类型和预算耗尽不能成为通过结论。
- 验收：详见下方最终执行记录。
- 未执行：新的 GPU 运行、native64、MI250、性能或 Polygeist/CKTI 共同案例。
- 未建立前提：输入报告忠实保留 AST、声明常量准确、外部 ABI 匹配完整源码；
  host 可达性、实际 launch、线程坐标和外部 intrinsic 语义尚未验证。
  `source_program_checked=false`、`deployable=false` 始终保留。
- 交付：代码、测试、协议和本交接一起直接提交；`artifacts/` 仍为本地忽略工件，
  不是已发布复现包。没有创建或操作 PR。
- 下一项：将具体源码类型转换绑定到目标 ABI/输入域，再继续连接线程坐标与
  launch；不能仅凭 block 条件字段值进入部署。

## 最终执行记录

主代理独立执行 `make check`：217 项通过；`git diff --check` 通过。

```bash
PYTHONPATH=src python3 -m wavebridge.configuration_check \
  artifacts/wb03-source-constructor-fields-01/report.json \
  --abi examples/abi/int32-conditional.json \
  --output artifacts/wb03-source-constructor-fields-01/configuration-model-check-01.json
```

退出码2，整体 `unknown`，符合门控预期：grid 的首实参仍 symbolic；block
在显式 ABI 条件下 `checked`，字段 x/y/z 为256/1/1。主代理读取输出断言这些
结果并核对全部三个实现哈希一致。复用既有源码报告，没有重跑 HIP 编译或 GPU。
