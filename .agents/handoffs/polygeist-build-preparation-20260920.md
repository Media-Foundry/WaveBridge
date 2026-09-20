# 固定 Polygeist 构建准备

- 日期：2026-09-20；分支 `wb03-source-ast`；父提交 `9ceed2e`。
- 主代理新增固定版本的前端构建脚本与文档，Sol 做只读源码核对和安全审查。
  使用 `make check` 验收，257 项通过；`git diff --check` 通过。
- 脚本默认 8 路编译、1 路链接，支持 1～16 jobs；核对 SHA 和干净工作树，
  独占创建新证据目录，拒绝源目录内构建。日志包括配置命令、工具入口哈希、
  编译过程；不修改上游、不安装系统依赖、不启动 GPU。
- 构建配置关闭 GPU runner/backend，只能用于准备前端对照；成功生成 cgeist
  后仍需真实 CUDA→MLIR 测试，不能直接声明 G1 或重定向成功。

## 下载状态与接续

实际命令：

```bash
git -C artifacts/toolchains/polygeist-cgo24 submodule update \
  --init --depth 1 --filter=blob:none llvm-project
```

第一次会话 53867 已终止，退出 128。远端已返回目标提交
`0b9310c6e4416ee48c07edfef81144e22850dfe7`，`rev-parse --verify ...^{commit}`
确认该提交对象存在；随后的 partial-clone 检出阶段 HTTP 408，最终报：

```text
fatal: could not fetch e200298f603e5eefce2dce79f18024e71b0c9bfa from promisor remote
fatal: Unable to checkout '0b9310c6e4416ee48c07edfef81144e22850dfe7' in submodule path 'llvm-project'
```

仅在确认原进程终止后才重试同一 submodule update；第二次会话 **28765**，
通过 `tee artifacts/polygeist-source-fetch-02.log` 保存输出，开启 pipefail。
交接时该会话尚未确认终态；下一轮先轮询同一 handle 或检查实际进程，
不能仅因没有输出重启。当前无 CMake/Ninja 构建进程。

获取成功后须确认子模块精确 HEAD、`submodule status` 前缀为空格和两仓工作树
干净，才运行 `experiments/baselines/README.md` 中的构建命令。
失败则保留原日志，区分网络/依赖与工具语义能力；不得替换成任意 LLVM 版本。

本轮直接 commit，不 PR、不推送；核心 G1 对照与自动 GPU 适配仍未完成。
