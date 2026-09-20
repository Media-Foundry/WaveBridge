# 实际构建与 CUDA 源码分析

- 日期：2026-09-20；分支 `wb03-source-ast`；父提交 `5317365`；中文、直接 commit、不 PR。
- LLVM 获取会话 28765 成功退出 0，精确子模块 HEAD 为
  `0b9310c6e4416ee48c07edfef81144e22850dfe7`；两仓干净状态已通过脚本核对。
- 下载日志 `artifacts/polygeist-source-fetch-02.log` SHA256：
  `9d35c00ab6259d4d435242928791750612d2043949dc16d60286502a9fedc6da`。
- 第一次构建会话 50706 退出 1：CMake 生成成功，Ninja 报 duplicate pool
  `link_job_pool`。`LLVM_PARALLEL_LINK_JOBS=1` 在重复载入的
  `HandleLLVMOptions.cmake` 中追加两次全局池。
- 未修改上游源码；构建脚本改用 `CMAKE_JOB_POOLS=wavebridge_link=1` 与
  `CMAKE_JOB_POOL_LINK=wavebridge_link`，清空 LLVM 的对应配置。
  原失败 `polygeist-cgo24-frontend-build/build.log` 保留，SHA256：
  `43122ea6ef5f8d6f2d412782c2e9d42229956dab54621160bdb45f359db8d826`。

## 正在运行，先续接不要重启

会话 **81182** 执行：

```bash
bash experiments/baselines/build_polygeist_frontend.sh \
  artifacts/toolchains/polygeist-cgo24 \
  artifacts/toolchains/polygeist-cgo24-frontend-build-02 8
```

配置已成功；rules.ninja 只有一个 depth=1 的 wavebridge_link 池。
构建已开始（计划 3296 项）；交接时尚未终止。下一轮轮询同一会话，
或核对 Ninja/编译器进程及 `build.log`，不能仅凭旧日志判断进程仍活跃。
配置日志 SHA256：`5e52fd626b53c75f5137e72a706f98cba9bddee025f3aa7bee17745ccccb2e24`。
不把正在构建记成成功，不重启已有构建，也不在完成前调用不存在的 cgeist。

## CUDA 源码真实分析

Sol 运行现有 `wavebridge.source`，使用真实 CUDA device AST、sm_70 和前轮隔离头文件。
不修改分析器，不读人工 oracle，不执行 GPU；主代理核对报告与实现哈希。

- `artifacts/wb03-cuda-source-01/report.json` SHA256：
  `c14cd85861be01ebe3edf261398ae1ac1b492e003c4be0ab2d05d9c1a5662260`。
- 同目录 `ast.json` SHA256：
  `6b806b9e2222faf267efc15760779ad9f10d3b8b40d7f0f825d79b3c0981c66d`。
- 完整实际编译命令在报告 `command` 字段；源 SHA 为
  `069811c2d7f40a9df0b2927837f4190ce9b7de9ad35e90e8f68a29bc78a52671`。
- 两条列循环均 recovered、step=256；local_contribution、normalization_output、
  row_prefix 均 recovered。报告 analyzed 不等于正确性通过，checked/deployable=false。
- reduction_discovery 的 block/xor_candidates 均为空、analysis_complete=false。
  Sol 对精确 helper 的补充调用诊断分别为 `update_not_three_argument_call` 和
  `unsupported_cast`；补充调用未保存为独立持久报告，不冒充主报告原字段。
- CUDA `_sync` 包含额外 mask，不能丢弃 mask 后直接套用三参数 HIP 模型。
  NVVM getter 名称不自动建立坐标语义；浮点、别名、参与及同步前提仍未证明。
- 同一案例的手工 CUDA 端口不计为新谱系，不能据此宣布 G1/G2 通过。

本轮 `make check` 258 项通过，含链接池配置回归；`git diff --check` 通过。
下一步先完成 cgeist 构建并保存产物哈希，再做共同输入→MLIR 对照；
同步保留 WaveBridge 在同一 CUDA 输入上的未知边界，避免设置不对称基线。
