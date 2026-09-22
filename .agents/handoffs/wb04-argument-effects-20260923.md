# 受限构造参数求值效果门控

- 日期：2026-09-23；分支 `wb03-source-ast`；基线 `bd7c876e70b4cb285601b0fd4554262069c165d4`。
- 用户约定：中文、直接 commit、验收后推送当前分支，无 PR。
- 实现：`verification/constructor_argument_effects.py`；测试为同名 Clang 测试及 fixture；接口文档在 `compiler/verification/README.md`。

## 实现和保证范围

Fresh 构造字段域检查之外，逐项核验参数求值。minimum 必须符合已有受限
精确函数体，callee/参数属性、DeclRef叶子、操作数存储期及作用域再独立检查。
仅接受同一普通非模板函数内的自动局部变量或直接形参；global/static/extern/
TLS（实际 `tls` 与 `tlsKind`）/引用/捕获/未知属性拒绝。作用域为目标所在
CompoundStmt 或外层前缀；for/if 初始化等额外作用域暂不支持。
存储类别白名单为缺省、auto、register；callee属性采用显式白名单，普通属性
必须无子节点，EnableIfAttr只能包含一个无子节点的bool prvalue true。
官方依据见 [Clang enable_if](https://clang.llvm.org/docs/AttributeReference.html#enable-if)。

签发仅指本次所选参数求值没有观测到外部存储写或地址逃逸至调用外。
内部const引用绑定、整数参数自身的存储初始化、标量临时量物化允许；不写成
绝对no writes。早先initializer历史、构造器本体、目标分配、外围cleanup、
异常、析构、后续逃逸及launch不在结论中。原数值子报告不回写升级。
有效完整AST、匹配整数ABI、已初始化可见对象及正常返回仍是前提。

## 本地验收

```bash
WB_NATIVE_CAPTURE_PLUGIN="$PWD/artifacts/capture-plugin-VKdLhn/libwavebridge_capture_plugin.so" WB_NATIVE_CAPTURE_COMPILER=/opt/AMD/aocc-compiler-5.1.0/bin/clang++ make check
WB_NATIVE_CAPTURE_PLUGIN="$PWD/artifacts/capture-plugin-VKdLhn/libwavebridge_capture_plugin.so" WB_NATIVE_CAPTURE_COMPILER=/opt/AMD/aocc-compiler-5.1.0/bin/clang++ PYTHONPATH=src python3 -m unittest discover -s tests -p '*clang*.py'
PYTHONPATH=src python3 -m unittest tests.test_constructor_argument_effects_clang
PATH=/opt/rocm/llvm/bin:$PATH PYTHONPATH=src python3 -m unittest tests.test_constructor_argument_effects_clang
make demo
```

602项CPU、135项Clang专项和demo通过；新5项在Clang17/23均通过。
测试同时断言global/TLS/static/extern等样例的数值子报告确实checked，但新
参数效果结论unknown，避免把旧分析器提前拒绝误称为新增门控覆盖。
未知存储类别、属性payload、叶子隐藏子节点、缺域及预算有回归。
日志位于 `artifacts/wb-vllm-argument-effects-A5Tix2/{check-final,clang,demo}.log`。

## 工件与下一步

执行 `PYTHONPATH=src python3 artifacts/wb-vllm-argument-effects-A5Tix2/replay.py`，
在完整固定 `artifacts/wb-vllm-native-Rw42Hh/ast.json` 上获得 checked，非投影。
输入SHA-256为 `c4642860faadf8920de29c3e79ca8dc984cd88af0e5ede7ce3f6de18b02c4d45`。
原始构造表达式 `0x38e44b58` 的position0关联minimum callee `0x38e445c8` 和
自动局部声明 `0x38e43878`；position1/2为精确默认字面量。输入域仍是外部
诊断假设 hidden_size∈[1,4096]，ABI为int32 signed/unsigned int32。
子报告 call_argument_effects 仍为not_established，新结论单列。
427.43秒（不含首次文件哈希），74个Python实现文件前后哈希一致。
报告 `artifacts/wb-vllm-argument-effects-A5Tix2/report.json` SHA-256：
`4b7bef8aeab71113ae9d14f679e2ce34fd2b929fa291f624a4ef6a1f909fe1bc`。
这是已有CUDA device-only编译视图的重放，不是新生产谱系或新的源码编译。

Checker SHA-256：`d3c7ab283df5bcf8747f350be29955bab1b94b87b9e975e5939316f3d2673b3b`。
完整重放脚本 `artifacts/wb-vllm-argument-effects-A5Tix2/replay.py`：
`31c1a4490b46afd930d604ec9092072b17cd3386e16dfac95c8904ff5c38e954`。
本轮没有GPU、新语料下载或候选部署；大工件本地保存、不入Git。
下一步须连接自动对象初始化及外围清理义务，之后再处理闭包调用和无写历史；
不能仅将各局部checked拼接成完整launch保证。
