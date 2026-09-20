# Polygeist 首次实际执行

- 日期：2026-09-20；分支 `wb03-source-ast`，基线 `fee65b9`，开始时工作区干净。
- 用户要求中文回复、直接本地 commit，不创建 PR、不推送。
- 既有构建会话 81182 正常完成，退出 0；未中断或重启。

## 实际命令与结果

```bash
bash experiments/baselines/build_polygeist_frontend.sh artifacts/toolchains/polygeist-cgo24 artifacts/toolchains/polygeist-cgo24-frontend-build-02 8
cmake --build artifacts/toolchains/polygeist-cgo24-frontend-build-02 --target clang-resource-headers --parallel 8
```

两条均成功；资源头是在原 Ninja 终止后构建。固定 Polygeist
`ba9953a08c9bc0965090911b67b2b1e1778cbb59`，LLVM
`0b9310c6e4416ee48c07edfef81144e22850dfe7`。仅前端构建，不启用 GPU 后端。

使用 `experiments/baselines/README.md` 中的完整命令运行真实 CUDA standalone。
第二次仅将 `--cuda-path` 改为 `artifacts/toolchains/cuda-polygeist-view-LRVuEu`。
新视图的 include/bin/nvvm 链接与旧视图相同，额外 lib64 链接指向
`../cuda-12.1-wheels/nvidia/cuda_runtime/lib`；旧视图、上游源码和 SDK 均未修改。
未用 stub 或改变 kernel/launch；均选择 `--function=*`。

| 本地工件 | SHA-256 | 结果 |
| --- | --- | --- |
| `artifacts/toolchains/polygeist-cgo24-frontend-build-02/bin/cgeist` | `fcbc0e8eb3466b4cde2521f2691c3fae534e13112d2b73b59a779b2e0a564903` | 构建成功 |
| `artifacts/toolchains/polygeist-cgo24-frontend-build-02/build.log` | `38570891b1368cb43170a9bb823963fe39b4859d1025c6d9f853afc50eb87c4c` | 最终 3296/3296 链接完成 |
| `artifacts/polygeist-frontend-izren5yd/report.json` | `caa6f58e47c424891d70955c71a50d389fa41144e68c7d70fe51e61116f1cf42` | tool_failed，returncode -6，无 IR；CUDA 安装识别失败 |
| `artifacts/polygeist-frontend-ksh3g5rh/report.json` | `63849001837c2ea9eb7e985cc575d799ecefdb9d514060ff21985ff4af33d4a8` | tool_failed，returncode -6，无 IR；头文件错误后断言 |

报告包含完整命令、cwd、原始 stdout/stderr、输入/工具/runner/调用器哈希。
第二次诊断明确包含 CUDA 版本新于部分支持的 11.8、texture 模板缺失，以及
GCC 13 basic_string 与 CUDA `__noinline__` 宏冲突。后续断言不能隔离为语义原因。
头文件闭包哈希尚未建立，本地 artifacts 不等于已公开复现包。

## 验证与下一步

本轮只改证据文档，核对报告和日志 SHA-256、执行退出码以及 `git diff --check`；
未重跑既有 273 项 CPU 测试，未生成或执行 GPU 候选，未做性能测量。
G1 未通过，不能声称 Polygeist 不支持本例。Sol 只读核查兼容环境，下一步先用
匹配的 CUDA/标准库头消除前置错误，再重试完整输入并检查实际 IR。
所有本轮修改直接本地提交，不推送；整体研究目标仍未完成。
