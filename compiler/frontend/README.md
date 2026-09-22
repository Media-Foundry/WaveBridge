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
可显式off进行不带依赖证据的诊断。同一次 AST 编译向 cc1 传递
`-dependency-file`、`-MT`、`-sys-header-deps`，包含系统头，
只接受单个wavebridge-inputs规则，保存原depfile、路径、文件大小和SHA256。
缺清单、缺文件、源文件前后hash变化均阻止required模式进入分析；失败编译仍
保持compile_failed而不是依赖成功。off明确not_requested，不静默升级完整性。

`observed`仅代表编译后读取依赖内容，不是冻结快照：并发修改无法完全排除。
实际 AST 子进程身份与完整 SDK 闭包尚未建立，
`compilation_input_closure_established=false`始终保留，不能作为完整缓存键。
required模式不接受用户覆盖依赖选项、response file或透传预处理选项，避免
另一套depfile设置覆盖采集器；复杂编译命令需要后续明确支持。
不依赖 driver 层 `-MF`：本机 HIP device-only 曾忽略该选项，导致缺清单并被拒绝；
同次 cc1 参数路径已通过实际 HIP 采集和 CUDA device-only 回归。

可选 `--toolchain-trace` 在 AST 采集前，用相同命令追加 `-###` 做独立 driver
dry-run，保留原始输出和命令，并观察唯一 cc1 任务中的后端文件哈希、target
triple/CPU、resource-dir 路径和显式 bitcode 文件哈希。多个 cc1 任务、参数歧义
或文件不可读时 trace 为 unknown，不选择某个任务冒充完整结果。不执行日志中的命令。
这只是 driver 计划与随后读取的文件，不证明实际 AST 使用了该后端或该文件内容；
resource-dir 不做递归闭包哈希。trace 失败保留原始原因，不抹去独立 AST 采集结果，
也不签发 checked 或部署许可。两次调用之间的环境变化仍未排除。

需要同次编译中的外部声明时加 `--full-translation-unit`，不再使用 symbol filter；
`--symbol` 仍用于核对入口是否存在。完整 HIP AST 可能很大：报告流式写出，
完整模式只保留解析后的 AST 与 stdout 哈希，不重复存储原始 stdout 字符串；
`stdout_retention=parsed_ast_only_not_verbatim` 明确这一边界。没有自动磁盘或内存预算管理。

## 可选原生捕获证据

`wavebridge.frontend.native_captures` 调用显式提供的编译器匹配插件，同次输出
完整 TU 与 `getCaptureFields` 捕获变量/闭包字段映射，避免跨进程裸 ID 拼接。
构建见 [原生插件](native/README.md)。它不改变默认 JSON 入口。

```bash
PYTHONPATH=src python3 -m wavebridge.frontend.native_captures input.cpp \
  --compiler /path/to/clang++ --plugin /path/to/capture_plugin.so \
  --compiler-arg=-std=c++17 --output artifacts/new-native-captures.json
```

输出必须为新文件；报告绑定源、插件、driver 的前后哈希、完整命令及同次依赖
观测。编译失败、超时、依赖缺失、输入变化和 envelope 解析失败不能 collected。
插件/AST 属于可信前端；collected 不检查元数据的语义正确性，更不证明运行时
对象身份、无写历史或 launch。复杂捕获保留 unsupported，不消费旧构造字段域。
Clang 插件 ABI 必须匹配；普通 CPU 测试可跳过原生集成，专项 CI 显式构建运行。
