# ROCm wrapper 实际编译

- 日期2026-09-20，分支 `wb03-source-ast`，基线 `76c4f1b`，开始工作区干净。
- 中文回复，直接本地commit，不创建PR、不推送；Sol只读分析兼容边界，
  主代理执行编译和补丁副本验证。
- 编译器为既有固定LLVM SHA的Clang16；HIP头来自SDK view `sdk-view-sx4rmd37`，
  CUDA为隔离11.8 runtime/nvcc。不是论文原ROCm5.3.4环境。

所有尝试用独占 `artifacts/polygeist-rocm-wrapper-*`；build.log保存set-x
完整命令与原始错误，管道启用pipefail。未执行生成代码或GPU。

| 目录后缀 | 退出码/结果 | build.log SHA-256 |
| --- | --- | --- |
| `gbiQoI` | 1，缺cuda_runtime_api.h | `0bf0d5f5c0f2c301b4362071a885c932306dab5eee9a2f5688832229fd980f23` |
| `RZuZS4` | 1，类型重复和memcpy缺声明 | `890c97a9a6306aefc0fbaab2fd3bb78dadac964be796fac42e126e82509cf757` |
| `HNH36e` | 0，上游DISABLE_CUDA_TO_ROCM纯HIP诊断 | `dcb4aebd9292481d9ce8b2d9d0c92e7ca710463861dfedd5881b62fa8dc3f821` |
| `bz8XFQ` | 0，完整wrapper隔离兼容副本 | `46a53b8b89669cba63e6e0dfa31dc8910886fa37f514bfaf8730872b1c2f69a2` |

纯HIP bitcode SHA：`617e855993a2f75330def2dafc157b8434967c31f3af5cd6a63fefc8412f4932`。
它不含CUDA属性适配，不能成为本任务的完整解法。

完整副本只补 `<cstring>`，在CUDA include前后临时重命名surfaceReference和
textureReference，保留原适配函数。上游原CPP SHA为
`4ce44c5becb83af6bdc724e435e529f9e7bad7847d2bf2fa40374b02cf813d1b`，
PGORuntime.h为`a78bc0b40794ac79220347f9012ea6a0ec1328e261d518cccaac43af68811cfc`。

- 隔离CPP SHA：`18e22503d90d4c49c661c23c833e8a8e33d080965e5d849a2efa47e0e3f30491`
- bitcode SHA：`8f80ad37cf1cc6829903a7c57c0ffe05709f7801511c9fabdf8404ba73dff4fa`
- 已提交补丁SHA：`53d5823af41c1a86f8316dddd67b1f662a1da95b8380672dd388b8623bb652c7`

两份成功bitcode均用同Clang `-S -emit-llvm <file.bc> -o <file.ll>` 重新读取，
退出0。完整副本的LL第2530行包含typed-pointer签名的
`mgpurtCudaGetDeviceProperties`定义；不是只生成空工件。未链接或执行函数。

## 未建立项与下一步

旧wrapper按CUDA字段大小memcpy HIP属性，字段尺寸和跨平台语义仍未核查；
编译通过不能防止尺寸不一致、未初始化未映射字段或错误能力解释。补丁未自动
接入完整后端，更不允许部署；不能仅用旧HIP头搭配新runtime绕过ABI检查。
后续需核对字段复制大小、实际后端配置及HIP CMake依赖；本机SDK view不是
完整开发包，未发现其中hip-config.cmake。完整ROCm编译和shuffle映射仍待执行。

验收：四次实际编译、两份bitcode重新读取、补丁 `patch --dry-run` 成功、
原上游 `git status --short` 干净、哈希与 `git diff --check`。本轮仅新增兼容
patch和记录，未重跑既有282项CPU测试；无数值/性能/GPU保证，G1未通过。
