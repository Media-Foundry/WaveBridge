# 构造器实现副作用门控

- 日期：2026-09-23；分支 `wb03-source-ast`；基线 `cc8ee28fd98f87d34fbe8fec54d6da8b4d040589`。
- 用户约定：中文，直接 commit，验收后推送当前分支，不创建 PR。
- 实现：`src/wavebridge/verification/constructor_effects.py`；完整 TU 精确关联构造器、record、字段和参数。仅接受普通整数字段的受限初始化、空 body；不支持效果保持 unknown。
- 回归：`tests/test_constructor_effects_clang.py` 与两个 constructor fixtures；正例、发布 this、复杂类型、身份错绑、未知属性、预算及输入不可变性。参数发布地址反例经 CPU 编译执行，说明安全构造器不等于安全调用表达式。

## 验收

```bash
WB_NATIVE_CAPTURE_PLUGIN="$PWD/artifacts/capture-plugin-VKdLhn/libwavebridge_capture_plugin.so" WB_NATIVE_CAPTURE_COMPILER=/opt/AMD/aocc-compiler-5.1.0/bin/clang++ make check
WB_NATIVE_CAPTURE_PLUGIN="$PWD/artifacts/capture-plugin-VKdLhn/libwavebridge_capture_plugin.so" WB_NATIVE_CAPTURE_COMPILER=/opt/AMD/aocc-compiler-5.1.0/bin/clang++ PYTHONPATH=src python3 -m unittest discover -s tests -p '*clang*.py'
PATH=/opt/rocm/llvm/bin:$PATH PYTHONPATH=src python3 -m unittest tests.test_constructor_effects_clang tests.test_constructor_escape_clang
make demo
PYTHONPATH=src python3 artifacts/wb-constructor-effects-CHfULJ/replay.py
```

592 项 CPU、125 项 Clang 专项和 demo 通过；相关 9 项在 Clang 17 与 23 均通过。
日志保存在 `artifacts/wb-constructor-effects-CHfULJ/`，最终全套为 `check-final.log`。
本轮无 GPU、无新源码采集、无新独立谱系或性能结果。

## 完整 TU 结果

输入固定 `artifacts/wb-vllm-native-Rw42Hh/ast.json`，而非投影：
SHA-256 `c4642860faadf8920de29c3e79ca8dc984cd88af0e5ede7ce3f6de18b02c4d45`；
canonical root `60cbcdf189f1c27b70504d223ae1512bb073ff129af87995a8c1855da4a0f2c4`。
这是既有 vLLM 开发输入及 CUDA device-only 编译视图，不是新的留出验证。

从原始构造表达式 `0x38e44b58` 重新关联构造器 `0x22738c88`，
所属 record `0x22738768`。实参恢复仍为 `unknown/one_or_more_arguments_unknown`，
但构造器身份已建立；不回写这一原始状态。副作用检查独立获得 checked，
仅允许 x/y/z 三个直接字段从对应整数形参初始化。
外部 ABI 为 int32 signed / unsigned int32，仍是显式前提。

重放 168.35 秒（不含首次文件哈希），五个实现文件前后哈希一致。

- 报告 `artifacts/wb-constructor-effects-CHfULJ/report.json`：
  `a504e7a1d35e4d40a5acb648562a89886deb909ae5cb6b02b893218412b44f7d`
- 重放脚本 `replay.py`：
  `5e142247f9a60bf48d690b0ca39e3c1db509563a1bc9b46bd13b93cdaabfb317`
- 新 checker：
  `e2d425bc076f8a6d65d31c814e5561d37de3d722f1ad3eed5f48f1c1ffc5042a`

## 局限与下一步

保证只覆盖所选构造器成员初始化式和 body，不涵盖调用参数、目标分配、
生命周期、清理、异常、析构、之后的闭包调用/逃逸及对象值保持。
整数转换的接受只表示受限效果，不表示数值不变。
`source_program_checked=false`、`deployable=false` 保持；未升级部署门控。
下一步应针对完整构造调用和后续闭包使用建立单独义务，不能仅拼接局部 checked。
提交范围仅为本轮代码、测试和文档；本地大工件不入 Git。提交/推送结果见最终交付。
