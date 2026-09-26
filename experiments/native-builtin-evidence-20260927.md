# 同次 AST 的 builtin 身份观察

基线 `37c812b`；日期 2026-09-27；分支 `wb03-source-ast`。

现有 native 插件增加可选 `builtin_calls`：由 Clang 原生 direct callee 与非零
builtin ID 分类，绑定同次 AST 的 call、callee 及有序实参 expression ID。
不通过源码名称前缀推断 builtin；数字 ID 仅在对应编译器版本内有意义。
旧工件缺字段不表示无 builtin；没有任何 checker 因本扩展放行调用。

## 真实采集

```bash
/opt/AMD/aocc-compiler-5.1.0/bin/clang++ -std=c++17 -fPIC -fno-rtti -shared \
  compiler/frontend/native/capture_plugin.cpp \
  -I/opt/AMD/aocc-compiler-5.1.0/include \
  -o artifacts/wb-native-builtins-JR99CL/libwavebridge_capture_plugin.so
```

使用 `wavebridge.frontend.native_captures.main`，source 为
`experiments/probes/builtin_values.cu`，compiler 及全部 compiler_args 原样读取
`artifacts/wb-pytorch-softmax-KhwXBa/config.json`；plugin 为上述新构建产物。
输出 `artifacts/wb-native-builtins-JR99CL/probe-final.json`，实际完整命令、输入
前后哈希和同次依赖观测在报告中。采集 `collected`，非 GPU 执行。

| 工件 | SHA256 |
| --- | --- |
| 插件源码 | `0c63bcf57a0ce7a989ec2fd50cc610d17a4c12620673e4bac5914f3e21e4266e` |
| 插件二进制 | `53c37dbe5e9593362ef4c8d7535d81bcb3a322afb1a45274467c611ea4903d3e` |
| 最终报告 | `ae5cf2a142e6790859a0d4340caa677dae1fc78609ba40f5d0d743f0f7f6aa82` |

首次 `probe.json` 在构建尚未完成时启动，正确记录 `input_unreadable`，没有
payload；保留失败记录，最终文件是构建完成后的新调用，不覆写首次工件。

完整 TU（包括 CUDA/标准库头文件）记录 536 个 visited direct builtin call。
这不是 kernel 动态可达数量。六个探针函数中：

- `wb_huge`：直接 huge_valf，0 个实参，native builtin ID 27。
- `wb_nan`：直接 nanf，1 个实参，native builtin ID 48。
- `wb_store_control`：也记录 huge_valf；该函数同时写内存，身份记录不证明无写。
- 两个 numeric_limits wrapper 和 external control 没有直接 builtin 记录。
  wrapper 的被调方法体需另行精确追踪，不能从这里的空列表推断其语义。

## 验证边界

真实 CPU Clang 测试核对同次 ID、声明、实参顺序、空字符串及普通函数/间接调用
负对照。插件身份记录是可信前端观测，不是独立证明；调用副作用、值语义、
实参求值、正常返回和整体覆盖没有建立。无新的生产 TU 留出或 GPU 结果。
后续消费者必须 fresh 绑定同次 AST，不能把新 ID 连接到旧冻结 AST 的 ID。
