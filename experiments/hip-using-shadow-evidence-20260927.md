# 真实 HIP using 引用展开身份重放

2026-09-27，基线`b1ae14a`。新增受限身份索引，两个scalar入口显式opt-in；
没有改动builtin结构/效果支持，没有提供新的效果假设，没有执行GPU。

## 实际命令与结果

```bash
PYTHONPATH=src:. python3 -u -m experiments.softmax_call_audit \
  --native artifacts/wb-hip-native-20260927-01/native.json --using-shadows \
  --output-dir artifacts/wb-hip-using-shadow-20260927-01
```

输入SHA256为`46ac52b1c672fadd0e5a66bb3ab380373e0cd69929713d96e7010f375a0cd63e`。
输出report.json SHA256为
`25f419054b13e416eb358ce27fbeb376176bb8b0d0d717e695efeba867d1048d`。
退出0，状态observed，输入、记录的src/driver依赖哈希前后一致。

| 普通声明 | ID | 引用展开匹配 | 身份查询结果 |
| --- | --- | --- | --- |
| exp | `0x2054bf90` | 全字段一致 | checked |
| log | `0x2054eb08` | 全字段一致 | checked |
| expf | `0x204e0d90` | 仅根loc.file单边省略 | checked |
| logf | `0x204e70d8` | 仅根loc.file单边省略 | checked |

这是`ordinary_identity_and_using_reference_representation_only`范围的结果，
不是四个函数已完成效果或数值检查。图清单仍保留原诊断边界；没有通过变更
诊断成功标记给生产checker签发语义结论。builtin_expf/logf结构检查仍为
unknown / builtin_structure_not_supported，source_program_checked与deployable
均false。输入AST未被删除副本或重写。

## 真实最小用例与回归

`tests/test_using_shadow_identity_clang.py`实际调用本机SDK Clang23：
`/home/husrcf/anaconda3/lib/python3.12/site-packages/_rocm_sdk_core/lib/llvm/bin/clang++`。
普通using函数转发及明确外部假设下的调用组合通过；写入wrapper和副作用
实参被拒绝。AST类型、body、target、位置、普通定义缺失/重复等负例是
显式标注的mutation fixture，不包装成新的编译器输出。

另有不依赖Clang的表示fixture，覆盖多个shadow、普通后代重复和原对象
返回。旧普通scalar入口回归保持支持；两模式策略哈希不同。
25项专项通过（0.325秒）。最终1238项CPU测试通过（97.463秒，无跳过）；
新引用展开专项使用上述SDK Clang23，既有native专项使用匹配AOCC17插件。
不称全量Clang23验收。make demo与diff通过，完成后再次核对报告中的driver
依赖和src哈希一致。日志为`/tmp/wb-using-shadow-check.log`与
`/tmp/wb-using-shadow-demo.log`。未核验远端CI。

GPT-5.6 Sol只读复核未发现P1，指出策略未绑定哈希和后代普通重复负例缺口；
均已在本次修订补齐。这是审查记录，不是一般正确性证明。

## 剩余工作

下一项是native一元float builtin身份与实参结构；在此之前不宣称HIP exp
效果链或循环保持性已通过。随后仍须分别建立效果协议、输入域和数值语义。
