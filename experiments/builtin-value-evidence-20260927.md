# 固定工具链 builtin 编译观察

日期：2026-09-27；基线 `de786e0`，分支 `wb03-source-ast`。

## 输入和重放

新增 `experiments/probes/builtin_values.cu` 是合成 CUDA 探针，不是生产 kernel。
使用冻结 softmax 配置的同一 AOCC Clang17 二进制及基础参数，另外设置 O0/O2、
LLVM IR 输出；不是重编译原始 softmax，也不是 W7900 执行。

```bash
PYTHONPATH=src python3 -m experiments.builtin_value_probe \
  --config artifacts/wb-pytorch-softmax-KhwXBa/config.json \
  --output-dir artifacts/wb-builtin-probe-jWB3VE/run-final
```

输出目录必须不存在。driver 固定配置/编译器 SHA，记录直接输入与自身依赖模块
前后哈希、命令、版本、执行状态、同次编译依赖清单及原始 IR。`observed` 仅表示
版本命令及两次编译完成、依赖观测成功且直接输入未变化，不代表预期 IR 模式自动验收。
头文件没有全部做前后双重采样；共享库、环境和工具链完整闭包尚未建立。

本地原始工件：`artifacts/wb-builtin-probe-jWB3VE/run-final/`（不入 Git）。报告 SHA256：
`0d138645c757f5177b46629fd3e06205197396b5a61bc66e65885927cade1567`。
历史配置及编译器 SHA 在 driver 中固定，报告还保存 source/module 哈希。

O0 IR SHA256：`745f3aa0b76ad90bb27e9fa000cdebeedb2d5717c5cbe69dd01df408b654b6dc`；
O2 IR SHA256：`49165f928829b6a300ffafc8e6bfdb2506dc09206e85340bb252d1014c567375`。

## 人工检查原始 IR 的结果

| 探针 | O0 | O2 |
| --- | --- | --- |
| `wb_huge` | 单条常量返回 | 单条常量返回 |
| `wb_nan` | 单条常量返回 | 单条常量返回 |
| `wb_limits_huge` / `wb_limits_nan` | 调用唯一包装体；被调体单条常量返回 | 包装展开，单条常量返回 |
| `wb_external_control` | 保留外部函数调用 | 保留外部函数调用 |
| `wb_store_control` | 保留 float 写入 | 保留 float 写入 |

返回指令分别为 `ret float 0x7FF0000000000000` 和
`ret float 0x7FF8000000000000`；这是 LLVM 文本表示，不能将十六进制字面长度
误写成返回值为 64 位。O2 四个常量包装的属性包含 `memory(none)`，写入负对照
是 `memory(argmem: write)`。这些都是该次工具链生成工件上的观察。

GPT-5.6 Sol 对上游 LLVM 17.0.6 的独立查证指出：
[Builtins.def](https://github.com/llvm/llvm-project/blob/llvmorg-17.0.6/clang/include/clang/Basic/Builtins.def)
登记 builtin 属性；
[CGBuiltin.cpp](https://github.com/llvm/llvm-project/blob/llvmorg-17.0.6/clang/lib/CodeGen/CGBuiltin.cpp#L2254-L2268)
在常量求值成功且无副作用时生成 ConstantFP。上游源码不是 AOCC vendor 二进制
的等同性证明，本轮结论以本地绑定工件为限。

## 边界与下一步

未运行 GPU、未重采生产 AST、未改变任何核心调用/循环门控。没有 source-program、
NaN payload 可移植性、fast-math 语义、机器码等价或部署结论。检查器不能按函数名
照单放行；外围实参求值和调用包装仍需要独立效果检查。

下一步将这些观察用于设计精确 builtin 身份、实参形状和外部工具链语义协议；
未知调用继续拒绝。原 WB-03 独立谱系及整核验收不因本轮关闭。
