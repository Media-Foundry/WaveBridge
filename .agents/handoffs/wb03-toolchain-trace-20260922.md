# 交接

- 日期、分支和基线：2026-09-22，`wb03-source-ast`，基线 `336add9`。
- 用户目标与约定：继续补全编译输入证据；中文回复，直接 commit，稳定后 push，不创建 PR。
- 完成：Sol 子代理实现 `frontend/toolchain_trace.py` 及单元测试；主代理完成
  collect/source 的 `--toolchain-trace`、真实 Clang 集成测试与文档。解析唯一
  driver dry-run 的 cc1 计划，记录后端文件哈希、目标、resource-dir 和 bitcode。
  未知/多任务/参数缺失/不可读均 unknown，日志中的命令从不执行。
- 实机发现并修复：HIP device-only driver 忽略 -MF，原 required 门控正确返回
  dependency_binding_failed。改为同次 cc1 的 -dependency-file/-MT/-sys-header-deps，
  不另外运行预处理器替代 AST 输入。新增无 CUDA SDK 的真实 device-only 回归。
- 实际验证：`make check` 481 项通过（4.521 秒），`make demo`、`git diff --check`
  通过；Sol 只读检查集成边界。真实 CPU Clang 为 AOCC 17，HIP driver 为 Clang23。
- 真实 HIP 命令：

  ```bash
  PYTHONPATH=src python3 -m wavebridge.frontend.clang_ast benchmarks/cases/llama-rmsnorm/baseline/rmsnorm_logical32.hip.cpp --compiler /home/husrcf/anaconda3/bin/hipcc --compiler-arg=--cuda-device-only --compiler-arg=--offload-arch=gfx1100 --symbol rms_norm_f32_logical32 --dependency-binding required --toolchain-trace --output artifacts/wb03-toolchain-trace-O8s4hK/final-ast.json
  ```

  最终 collected，依赖 observed：320 个文件；trace observed：amdgcn-amd-amdhsa、
  gfx1100、Clang23 和 7 个 bitcode（包括 OCML/OCKL）。最终报告 SHA-256：
  `a05d0fe560702fddcc580332d2b54e96434a2c157203c3d8eb0c1091390457d1`。
  同目录 `ast.json` 保留 driver -MF 路径失败，哈希
  `bd37e81e3f8095b94eec2cd806129932b47f9df8bf5bc8ad660317acf002d490`；
  `ast-cc1-deps.json` 是首次修正成功记录。工件忽略、不上传 Git。
- CI：通过 gh 核验基线 336add9 的 run35730352101，Python3.11/3.12 与
  clang-source-regressions 均 success；没有将该结果继承给新提交。
- 未执行：GPU、数值/性能实验、完整 HIP TU 重新关系分析、本次远端 CI 验收。
- 范围：仅 symbol-filtered AST 和依赖观测、独立 dry-run 计划任务；不是实际
  AST 子进程身份认证。两次调用间环境可变化，文件内容也不是冻结快照。
  resource-dir 仅记录路径，不递归哈希 SDK/共享库。closure、checked、deployable
  不因这些证据升级。未声称 HIP/SDK 语义版本或波宽已验证。
- 提交计划：上述实现、测试和文档一起提交并 push 当前分支，结果以 Git 为准。
- 下一项：在同次 AST 采集中核对 driver 执行记录与计划视图，明确动态库/SDK
  证据边界；随后对完整 TU 重采集，回到独立谱系的类型转换支持与受检候选路径。
  不通过无限增加证据模块替代真实适配闭环；WB-03 仍未完整验收。
- 阻塞：本轮无阻塞。
