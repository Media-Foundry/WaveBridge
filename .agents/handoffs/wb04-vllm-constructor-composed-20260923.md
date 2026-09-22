# 完整 TU 构造组合重放与参数效果边界

- 日期：2026-09-23；分支 `wb03-source-ast`；实现基线 `0aab78120de124b3372abbaede8e61d228ba54f8`。
- 中文回复、直接 commit、推送当前分支，不创建 PR。
- 本轮新增验证证据、动态 TLS 真实源码回归及文档，未修改 checker 实现。

## 完整 TU 实际执行

```bash
PYTHONPATH=src python3 artifacts/wb-vllm-constructor-composed-YQYwZT/replay.py
```

输入 `artifacts/wb-vllm-native-Rw42Hh/ast.json` SHA-256：
`c4642860faadf8920de29c3e79ca8dc984cd88af0e5ede7ce3f6de18b02c4d45`。
从同次完整 AST 选择原始构造表达式 `0x38e44b58`；动态参数 `0x38e44ae8`
引用声明 `0x38e43878`，外部假设其 int 值为 `[1,4096]`。
ABI 显式假设 int32 signed / unsigned int32；没有把该域称为源码推导结果。

组合 fresh 恢复身份、检查构造器效果、检查 minimum 表达式和字段域，结果
checked：x∈[1,1024]、y=z=1。动态实参原始恢复仍 unknown，不升级原报告。
运行 432.26 秒（不含第一次输入文件哈希），73 个 Python 实现文件前后哈希
一致。检查器分别哈希完整 root，组合成本仍较高；没有使用投影或外部成功报告。

- `report.json` SHA-256：`2bcbd53fc6e2fc8c217d598b38ec1c6b49568bc538e26a6d5fc626c8f1c1c6ef`
- `replay.py` SHA-256：`30297f743b338f8c90b87db741e39208b53cd1973d7605c80ab5afe9726926bf`
- 上述两文件均在 `artifacts/wb-vllm-constructor-composed-YQYwZT/`。

这是已有固定 vLLM 开发输入和既有 CUDA device-only 编译视图的重放，不是新
独立谱系、重新编译或 GPU 运行。没有建立字段从构造到实际 launch 的值保持。

## 参数效果反例及验收

扩展 `tests/fixtures/constructor_value_effects.cpp`：动态 thread_local int 的
初始化函数增加全局计数器并返回7；minimum和普通构造最终字段值为7。
CPU main 检查首次使用前计数0、首次使用后1、第二次仍1，说明数值正确不等于
参数求值无写入。真实 AST 记录 `tls: dynamic`。对应组合仍 checked/value=7，
但 call_argument_effects/post_construction_escape 始终 not_established；
这是支持当前保证边界的反例，不是新发现的值域错误放行。

```bash
WB_NATIVE_CAPTURE_PLUGIN="$PWD/artifacts/capture-plugin-VKdLhn/libwavebridge_capture_plugin.so" WB_NATIVE_CAPTURE_COMPILER=/opt/AMD/aocc-compiler-5.1.0/bin/clang++ make check
PYTHONPATH=src python3 -m unittest tests.test_constructor_value_effects_clang
PATH=/opt/rocm/llvm/bin:$PATH PYTHONPATH=src python3 -m unittest tests.test_constructor_value_effects_clang
make demo
```

597 项全套通过；相关5项在 Clang17/23均通过（含真实 CPU 执行）；demo通过。
全套日志保存在上述目录 `check-final.log`。

## 下一步与未建立项

完整调用参数效果门控应fresh复用minimum数值关系，但还需检查 caller declaration
的作用域、存储期（含实际tls字段）、属性与捕获路径；未知global/static/TLS不能
仅凭整数域放行。literal temporary与外围ExprWithCleanups须区分。
构造目标分配、生命周期、清理、异常、析构、后续闭包使用、历史值保持和launch
仍未建立，source_program_checked/deployable保持false。未启动GPU作业。
所有大工件本地保留，不提交；本轮提交范围仅测试、文档与本交接。
