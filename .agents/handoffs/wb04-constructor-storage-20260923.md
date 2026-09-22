# 构造字段域存储形状修复

- 日期：2026-09-23；分支 `wb03-source-ast`；基线 `4d6df79c3d2e613e3c2c9bd27669eef37881c4d6`。
- 用户约定：中文、直接 commit、验收后推送当前分支，无 PR。
- 实现：`constructor_source_check.py` fresh 接入 `constructor_effects`，核对同 root 中精确 constructor/record 后才输出字段域。
- 测试：`test_constructor_value_effects_clang.py` 和 fixture；真实 TU → 不 mock 组合检查 → CPU 实际执行。

## 实际反例与修复

`typedef struct NarrowBits { unsigned x:3; NarrowBits(unsigned v):x(v){} } NarrowBits;`
调用 `NarrowBits value(99)`：基线报告 checked/value=99，而 CPU 实际值为 3。
同一 AST 的修复后报告为 unknown/constructor_effects_not_checked，子报告
reason=record_field_shape_unsupported，不再输出 fields。普通 unsigned 值仍为99，
volatile 对照仍unknown。不是仅修改报告措辞，也没有实现 bitfield 的新语义。

复现命令：

```bash
PYTHONPATH=src python3 artifacts/wb-field-storage-dvh5vV/reproduce.py
WB_NATIVE_CAPTURE_PLUGIN="$PWD/artifacts/capture-plugin-VKdLhn/libwavebridge_capture_plugin.so" WB_NATIVE_CAPTURE_COMPILER=/opt/AMD/aocc-compiler-5.1.0/bin/clang++ make check
PATH=/opt/rocm/llvm/bin:$PATH PYTHONPATH=src python3 -m unittest tests.test_constructor_value_effects_clang tests.test_source_constructor_clang
make demo
```

旧实现通过 `git show` 固定基线加载，而非使用不断变化的分支。复现目录保存
完整 AST 采集报告、前后结果、编译命令及 CPU 断言（ordinary=99/narrowed=3）。
报告 `artifacts/wb-field-storage-dvh5vV/report.json` SHA-256：
`a1397871ec8d4c2447a0be976f313a0e881b5950a202f849d4b6a9dccc136a95`。
新组合实现 SHA-256：`f191c493c3287a4127851fc8f41cddb9547f44288a3e595d926ca755dcba9daa`。

596 项 CPU、demo 通过；12 项相关真实 Clang 测试在 17/23 均通过。
未重新执行完整 vLLM TU、GPU 或性能实验；历史局部构造器结果不等于新组合通过。
重复完整 root 哈希带来的组合成本尚未优化，不引入信任调用者报告的捷径。

## 边界和下一步

这次补上字段域检查真实存储形状的必要条件，并非完整调用无逃逸。
顶层 call_argument_effects/post_construction_escape 保持 not_established；
source_program_checked/deployable 保持 false。下一步仍需完整调用参数与清理、
闭包使用及对象值保持证据。工作树仅本轮文件；本地大工件不提交。
