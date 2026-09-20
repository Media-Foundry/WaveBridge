# CUDA 块级归约调用接入

- 日期：2026-09-20；分支 `wb03-source-ast`；父提交 `68a1d93`。
- Sol 定位真实 AST 并实现 barrier callee 专用 BuiltinFnToFnPtr 记录；主代理
  审查、补参数位置拒绝测试、完整重跑源码入口、核对实现/AST 哈希。
- 仅修改受限调用结构支持，没有根据函数名赋予 barrier 语义，没有改 checker。
  测试中的 `__builtin_trap` 故意不是 barrier：只测试 AST 结构，绝不执行，
  且断言语义仍 not_established，防止把形状匹配宣传成语义识别。

## 验收

实际入口沿用前轮 CUDA device 编译参数，独占输出
`artifacts/wb03-cuda-block-01/`；具体命令保存在 report.json 的 command 字段。

- report.json SHA256：`92e1d0a3ad54609ef0bd61a04346cfeb94a9f5f3116f6f9405b6fe54f1c9a8e0`
- ast.json SHA256：`bbac74589a47fc3cd28288f97915afc36a7fb57c4c71de78a7bbdaa3c93aeeef`
- 自动 XOR 候选1，block候选1；block_threads256、width32、writer_lane0，七阶段完整。
- block 的 reduce_declaration_id 与 XOR 的 function_id 精确相等。
- barrier callee 在源码 offset895，保留 `<builtin fn type>`→`void (*)()` 转换。
- checked/deployable=false，barrier_semantics=not_established，非整核正确性结论。
- `make check`：273项通过；全部实现哈希、AST字节哈希与报告一致；diff-check通过。

另外从固定 Polygeist 源码确认 O0 仍运行 CSE/canonicalization/Mem2Reg，
runner 新增 pipeline 标签，不能把它当不做变换。build.ninja 核实资源头输出到
`lib/clang/16.0.0/include`，已修正待执行命令，不使用此前推测的 `lib/clang/16`。

## 继续工作

Polygeist 构建会话仍为 **81182**，目录
`artifacts/toolchains/polygeist-cgo24-frontend-build-02`，本轮已经轮询确认活跃，
约1885/3296任务。下一轮继续该handle或检查实际进程，勿重复启动。
成功后单独构建 clang-resource-headers，再运行记录器；尚未获得同例 MLIR。
不在同一目录并发启动两个 Ninja，不把正在编译或 CPU 测试记为基线执行通过。

本轮直接 commit，不 PR、不推送；无新GPU执行，无自动候选部署，G1仍未完成。
