# 交接：源码入口的归约候选发现

- 日期、分支和基线：2026-09-20，`wb03-source-ast`，`2a8a52c`。
- 用户约定：中文；直接 commit，不创建 PR；本轮未推送。
- 完成：`analysis/reduction_discovery.py` 从入口按精确直接调用 BFS 发现候选，限制 64 个函数和 512 次结构尝试；`source.py` 接入并绑定实现哈希。候选为结构恢复报告，不签发源码检查结论。
- 验证：`make check` 158 项通过，`git diff --check` 通过；真实 Clang 入口 fixture 不需要 helper ID，并排除不可达诱饵。
- 真实 HIP 命令：`PYTHONPATH=src python3 -m wavebridge.source benchmarks/cases/llama-rmsnorm/baseline/rmsnorm_logical32.hip.cpp --compiler /home/husrcf/Code/ProtBind/wavebridge/artifacts/toolchains/sdk-view-sx4rmd37/bin/hipcc --compiler-arg=--cuda-device-only --symbol rms_norm_f32_logical32 --int-bits 32 --output-dir artifacts/wb03-source-reductions-02`。
- 结果：9 个已定义可达函数、3 次结构尝试、1 个块级和 1 个 XOR 候选；block256/width32、XOR offsets16/8/4/2/1；23 条 unresolved，`analysis_complete=false`。报告中的 AST 和全部实现哈希已核对匹配。
- 首轮工件 `wb03-source-reductions-01` 与代码修改并发，不用于最终版本验收；保留未覆盖。
- 边界：语法直接调用路径不是完整动态调用图；未知调用、坐标/转换/intrinsic 语义、整核数据贡献及 launch 一致性尚未建立。无新 GPU 执行或性能结论。
- 下一步：按最终报告分类 23 条 unresolved，针对首例所需的属性 getter 和外部 intrinsic 建立有证据的语义接入；连接循环贡献、归约和输出关系。不要因局部候选被发现而宣称 G2/G3 已通过。
