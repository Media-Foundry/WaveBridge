# 源码接入

计划提取源码位置、编译选项、宏/include 依赖、线程索引、intrinsic 和 kernel/launch 关联。必须固定源语义与目标工具链。遇到无法解析的调用不以普通算术代替。

当前实现：`src/wavebridge/frontend/fixture.py` 接入人工 JSON 模型；
`src/wavebridge/frontend/clang_ast.py` 从真实编译器收集 JSON AST 和函数位置。
后者不是关系恢复器，不读取人工 oracle，也不签发语义或部署结论。

首例的编译视图、尚缺的调用闭包及分析义务见 [RMSNorm 支持边界](rmsnorm-support.md)。

```bash
PYTHONPATH=src python3 -m wavebridge.frontend.clang_ast \
  benchmarks/cases/llama-rmsnorm/baseline/rmsnorm_logical32.hip.cpp \
  --compiler /path/to/hipcc --compiler-arg=--cuda-device-only \
  --symbol rms_norm_f32_logical32 --output artifacts/new-ast-report.json
```

`collected` 仅代表收到了对应声明的真实 AST；编译失败、超时、解析失败、缺工具和
无对应声明分别报告。输出文件必须不存在。AST 原文保留多个 JSON 根，设备视图
由显式参数确定，不根据函数名猜测。

低层collect/CLI可选`--dependency-binding required`；`wavebridge.source`默认required，
可显式off进行不带依赖证据的诊断。同一次AST编译增加`-MD -MF -MT`，包含系统头，
只接受单个wavebridge-inputs规则，保存原depfile、路径、文件大小和SHA256。
缺清单、缺文件、源文件前后hash变化均阻止required模式进入分析；失败编译仍
保持compile_failed而不是依赖成功。off明确not_requested，不静默升级完整性。

`observed`仅代表编译后读取依赖内容，不是冻结快照：并发修改无法完全排除。
实际wrapper后端、resource-dir/bitcode追踪尚未接入，
`compilation_input_closure_established=false`始终保留，不能作为完整缓存键。
required模式不接受用户覆盖依赖选项、response file或透传预处理选项，避免
另一套depfile设置覆盖采集器；复杂编译命令需要后续明确支持。

需要同次编译中的外部声明时加 `--full-translation-unit`，不再使用 symbol filter；
`--symbol` 仍用于核对入口是否存在。完整 HIP AST 可能很大：报告流式写出，
完整模式只保留解析后的 AST 与 stdout 哈希，不重复存储原始 stdout 字符串；
`stdout_retention=parsed_ast_only_not_verbatim` 明确这一边界。没有自动磁盘或内存预算管理。
