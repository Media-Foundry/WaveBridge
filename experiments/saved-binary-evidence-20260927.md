# 历史基线二进制的设备代码核验

日期：2026-09-27；基线提交 `129e5d8`。

## 对象与方法

核验 `artifacts/wb02-20260926T154202Z-d8e8d1/rmsnorm_logical32`，其SHA256
`17955611397d5bcc59cdb67c711059d600d6fa10515ec59cf9bbd970807c8442`
与历史run报告及build_binding相同。该run历史记录为W7900上的3×777基线；
本轮没有再次执行binary或启动GPU，也没有重新编译源码。

先以LLVM工具手工提取并读取，再用snapshot-first入口完整重放；两次提取的
device code object均为5008字节，SHA256
`b5c8b8abaf3972c79b7008a50116d83d7a4d1a4ae53dbe8f76b5e397ac4c9977`。
LLVM `--offloading` 会写出bundle，因此第一次生成的两个文件已移到
`artifacts/wb-saved-binary-X98JfN/`，没有删除原二进制。新入口始终先复制
快照，采集只在新目录进行。

可重放的采集报告在 `artifacts/binary-observation-aapbsz8o/report.json`，SHA256
`1c21353cccdf9bbb66f5910f1740015dea68698e720e02756dacea24c4dc9d63`。
其中保存完整工具路径/版本/摘要、命令、输出、二进制快照、code object，
以及输入前后摘要一致的观测。反汇编输出会包含被读取路径；不同提取目录下
文本摘要不同，不表示设备对象字节不同。

最终入口增加报告对象结构与重复键拒绝后，又以同一binary实际重放成功，
code object摘要不变。最终报告 `artifacts/binary-observation-i0z96js_/report.json`
SHA256 `614e9b19c21a7a032b4dd9331409b0612f5a60b4eda104329a27e6fa5a740cc9`。
前一份报告与初次手工提取均保留，不覆盖历史记录。

## 静态观察结果

保存对象中kernel符号为 `_Z22rms_norm_f32_logical32PKfPfif`，入口0x1700。
元数据给出同名descriptor、四个参数（offset0/8/16/20）、target gfx1100、
wavefront_size 32。`.gfx1250_revision`等附加字段不能被当作实际设备身份；
目标以明确target与ELF信息核对，实际设备另依赖历史运行证据。

| 地址 | 观察到的操作 | 对当前模型的作用 |
| --- | --- | --- |
| `0x178c` | `v_fmac_f32 v4,v6,v6` | 保存机器码的局部平方累计是FMA形状，不是分离乘加 |
| `0x1960`–`0x19c0` | division scaling、rcp、FMA、fixup | 除法lowering是多指令链；不能只凭形状宣布正确舍入 |
| `0x19c8` | `v_add_f32 v1,s3,v1` | 分母加epsilon，s3来自参数加载 |
| `0x19d0`–`0x1a0c` | 阈值比较、缩放、选择和rsq | 含非正规数缩放/恢复路径；rsq位于`0x19e8` |
| `0x1a74` | `v_mul_f32 v6,v5,v6` | 输出使用scale与加载输入相乘 |

这与前面的compile-only观察一致，但这次直接读取的是与历史运行记录绑定
的二进制内嵌代码，而不是另一次从源码生成的汇编。GPT-5.6 Sol独立只读核查
了符号、元数据、指令地址及保证边界。

## 未解除的义务

二进制摘要匹配记录，并不证明记录本身可信或动态loader选择了该code object。
本核验没有穷尽所有动态路径、active lanes、共享内存可见性、输入地址/数据，
没有证明各条指令误差律、ISA契约实际适用或整核等价。FP模式元数据也不能
替代运行时观察。候选native64未执行，reference及冻结容限未变。

新入口只返回observed；metadata_semantically_validated、actual_fp_laws_verified、
dynamic_loader_selection_verified、numeric_contract_checked与deployable均false。
下一步应沿这个实际code object建立所需的指令级对应或可信lowering前提，
不能用本次静态清单替代完整适配门控。
