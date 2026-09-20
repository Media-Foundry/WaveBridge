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
由显式参数确定，不根据函数名猜测。依赖头文件闭包尚未哈希，不能作为完整缓存键。
