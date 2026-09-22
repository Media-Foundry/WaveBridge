# 原生表达式清理观察与析构反例

- 日期：2026-09-23；分支 `wb03-source-ast`；基线 `59102106b560e2c8eb2c7f111678c4e5fab09464`。
- 用户约定：中文、直接commit、验收后推送当前分支，无PR。
- 修改：既有 `capture_plugin.cpp` 增加原生 ExprWithCleanups 观察；Python collector仅补充限制声明；新增fixture、4项真实Clang/CPU测试与文档。

## 接口与语义

同一 `clang-native-captures/v1` envelope 中新增可选 `expression_cleanups`，
记录expression_id/subexpression_id/num_objects/cleanups_have_side_effects。
原生指针去重，cleanup_coverage明确visited_expressions_not_exhaustive。
保持旧captures和schema兼容；旧工件缺字段不是没有清理的证明。

本机Clang17 `ExprCXX.h` 的 CleanupObject 为 BlockDecl/CompoundLiteralExpr
指针union，getNumObjects数的是该辅助数组，不是C++临时对象析构事件。
fixture中scalar_temporary和destructor_temporary均num_objects=0；前者flag=false，
后者flag=true且AST含CXXBindTemporaryExpr。CPU实际执行确认后者析构增加全局
计数器。说明未来门控不能只检查数量。flag仍是可信前端观察，不是独立证明。

## 构建与验证

最终源码SHA-256：`2c53688068ae9e30d8968efe84317e4f5fd828d9789908d751588ce5fe97e1bb`。
最终插件 `artifacts/capture-plugin-cleanups-gYQ3gz/libwavebridge_capture_plugin.so`：
`8b56a3b0e4241a59408d4d796da0e3ce7e931e7c8448db2630c1f0d876c2a3db`。
AOCC17构建命令：

```bash
/opt/AMD/aocc-compiler-5.1.0/bin/clang++ -std=c++17 -fPIC -fno-rtti -shared compiler/frontend/native/capture_plugin.cpp -I/opt/AMD/aocc-compiler-5.1.0/include -o artifacts/capture-plugin-cleanups-gYQ3gz/libwavebridge_capture_plugin.so
WB_NATIVE_CAPTURE_PLUGIN="$PWD/artifacts/capture-plugin-cleanups-gYQ3gz/libwavebridge_capture_plugin.so" WB_NATIVE_CAPTURE_COMPILER=/opt/AMD/aocc-compiler-5.1.0/bin/clang++ make check
WB_NATIVE_CAPTURE_PLUGIN="$PWD/artifacts/capture-plugin-cleanups-gYQ3gz/libwavebridge_capture_plugin.so" WB_NATIVE_CAPTURE_COMPILER=/opt/AMD/aocc-compiler-5.1.0/bin/clang++ PYTHONPATH=src python3 -m unittest discover -s tests -p '*clang*.py'
make demo
```

606项CPU、139项Clang专项和demo通过；native capture/cleanup定向15项通过。
日志 `artifacts/cleanup-plugin-9XbVv4/{check,clang,demo}.log`。
初次联调使用了字段名修改期间编译的旧SO，出现缺num_objects的KeyError；
后续冻结源码并使用上述最终SO重跑通过。旧SO保留，不作为最终验收工件。

固定fixture完整采集命令：

```bash
PYTHONPATH=src python3 -m wavebridge.frontend.native_captures tests/fixtures/native_cleanups.cpp --compiler /opt/AMD/aocc-compiler-5.1.0/bin/clang++ --plugin artifacts/capture-plugin-cleanups-gYQ3gz/libwavebridge_capture_plugin.so --compiler-arg=-std=c++17 --output artifacts/cleanup-plugin-9XbVv4/cleanups.json
```

该报告SHA-256：`e9be2882372d8658cd4f0bee0df53e872cacec8397c8328006da9506268ef991`。
保存源码、编译器、插件、依赖和执行信息；4项cleanup观察使用同次AST指针ID。

## 未建立与下一步

没有新GPU执行，也未重新采集vLLM大TU；历史大TU缺这些字段，不能补猜。
尚未将观察接入初始化门控。下一步应绑定精确自动对象、构造表达式和外围
ExprWithCleanups，并明确清理API的可信基础；不能从flag或缺失记录直接推导
完整程序、异常路径、生命周期、历史值保持或launch正确性。
大工件本地保留，提交范围仅源码、测试及文档。
