# 数组 helper 的受限写入范围检查

2026-09-27，wb03-source-ast，基线8a299ae。无GPU、无生产AST重采。

```bash
PYTHONPATH=src:. python3 experiments/softmax_array_effects.py \
  --native artifacts/wb-column-builtins-twz82w/native.json \
  --output artifacts/wb-array-effects-aUY5oM/replay.json
```

固定native SHA256：
`317b1a438bc13845cf76b5aa7461db4db2081b402c457a85c4160fdd7257c027`。
输出SHA256：
`c6ee069115f5b0072fa88c19284b5f5b8e289e3c22daa6d39ddad90dd721f47a`。
输入及实现前后哈希一致（inputs_unchanged=true）。

## 支持子集及真实结果

`array_call_effects.check`从完整TU精确绑定直接void(float*)调用、形参和
caller自动float[N]数组（1≤N≤4096），以及同一直接函数体内已声明的
独立自动int/const int对象。只支持helper自动标量和该数组元素的显式写入；
指针/引用局部、参数重赋值、全局写入、解引用及其他不支持效果保持unknown。
类型判断复用语义类型入口，未展开别名不按普通标量接受。

正常返回、源执行有效、存储存活且不同、访问在对象内及无异步干扰仍是显式
前提。未证明数组边界、运算数值、归约/通信正确性或物理波宽。

实际调用0x1954ab18 → helper 0x195316e8，形参sum 0x19531658，
绑定caller数组max_value 0x195485f8（float[2]）和保护对象local_idx
0x19546950。7处静态写入位置中，4处为局部初始化、2处为局部增量，
1处为sum[i]赋值；不是执行次数统计。

explicit_write_targets_checked=true，但status=unknown，
reason=unresolved_call_or_lifecycle_effects。以下五项保留：

| 义务 | AST ID |
| --- | --- |
| 局部Max对象生命周期 | 0x19538580 |
| 构造表达式 | 0x19538618 |
| WARP_SHFL_XOR调用 | 0x19538c70 |
| 默认实参求值 | 0x19538cf8 |
| Max::operator()调用 | 0x19538fa0 |

protected_storage_preserved、array_bounds_checked、source_program_checked、
deployable均为false。该checker尚未接入历史保持入口；上轮loop入口域仍
未建立。不能把“显式写入目标已分类”改称“归约无副作用”。

## 回归与下一步

GPT-5.6 Sol新增5项真实Clang测试并只读复核：自动数组与局部写入正例；
全局/参数/引用/解引用负例；未知调用保留部分结果；pointer/offset/超预算
数组/不同caller对象拒绝；精确ID和预算边界。

验证日志位于`artifacts/wb-array-effects-aUY5oM/{check,demo}.log`。
完整验证结果见docs/status.md本轮条目。远端CI未核验。

下一步从同次AST逐项检查operator、构造/生命周期与shuffle/defaultarg，
再考虑接入历史保持；不得使用虚假的全局无写假设替代真实数组更新。
