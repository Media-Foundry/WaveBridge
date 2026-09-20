# 掩码恢复与 Polygeist 执行入口

- 日期：2026-09-20；分支 `wb03-source-ast`；父提交 `9624e75`。
- 用户要求中文、直接 commit、不 PR；本轮不推送、不合并。
- Sol 扩展 `xor_reduction.py` 与专用测试；主代理审查并增加 CLI 的不支持掩码
  不调用路由 checker 回归，重跑真实源码入口，核对全部实现哈希。
- 新四参数形式仅支持 width32、显式 uint32 全掩码字面量。原三参数路径保留。
  mask 原 AST、类型、范围保留；参与、收敛、intrinsic、FP 等仍是未建立前提。
- 主代理新增最小 Polygeist 前端执行记录器及七项 mock 状态测试；命令与状态
  协议见 `experiments/baselines/README.md`。默认 whole-input `--function=*`。
  `emitted_unverified_ir` 不表示文件合法或语义正确；尚未执行真实 cgeist。

## 实际源码验收

沿用前轮 CUDA 参数，用 `wavebridge.source` 完整重新编译分析，输出独占目录
`artifacts/wb03-cuda-source-mask-01/`。报告 `command` 保存实际编译命令；
源码 hash 与原 CUDA 端口一致，未读取 oracle，未生成/执行 GPU 候选。

- report.json：`1b9f127edcf03177fd2bd7a322c704ab01d32bba65fbfb463ff8ce270381c1a5`
- ast.json：`d7a6b705a24249005472efb3f88f37088238b413032d6bc8b45f0e64a067f3bd`
- xor_candidates：1；width32、offsets16/8/4/2/1、mask4294967295；
  mask 类型 unsigned int，external_shuffle_semantics=not_established。
- block_candidates：0；全局 checked/deployable=false。
- 这是同一谱系的 CUDA 端口，不增加真实语料谱系，也不证明 G1。

主代理 `make check`：270 项通过；`git diff --check` 通过。
真实 Clang CPU 声明 fixture 验证改名与参数结构，不作为 GPU benchmark。

## 仍运行的构建

会话 **81182**，目录 `artifacts/toolchains/polygeist-cgo24-frontend-build-02`。
本轮已实际轮询，约1480/3296任务时仍运行；下一轮必须继续核对同一会话/进程，
不根据旧日志推断存活、不重复启动。日志 `build.log`，源码版本固定且没有修改。
构建完成后先建 `clang-resource-headers`，再用新记录器执行完整共同 CUDA 输入。
资源头目标已从生成的 build.ninja 核实存在，但尚未单独构建。

后续保持公平对照：若 cgeist 成功输出文件，独立检查其中 kernel、launch、
shuffle、shared/barrier 和未解析外部调用；不能凭退出码或文件存在判断等价。
