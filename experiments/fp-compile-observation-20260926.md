# RMSNorm 浮点编译观察（非 GPU 验收）

日期：2026-09-26；基线 `7799c05`，分支 `wb03-source-ast`。
目的：检查 typed-AST 局部值条件模型尚未覆盖的实际编译行为，**不改变冻结
baseline、数值容限或部署状态**。本轮没有执行 GPU，也没有运行数值比较。

## 输入与工具链

- 源：`benchmarks/cases/llama-rmsnorm/baseline/rmsnorm_logical32.hip.cpp`，
  SHA256 `7284151f806d710ff3396b94b62b3ec35d5bef3f44815e1e7837aad66dc85823`。
- 离线候选：`artifacts/wb-source-candidate-1sKytL/candidate.hip.cpp`，
  SHA256 `2bf010241f268b2bbc96e77e67a9e888690ee9bd81ae676fdaa80f9072c987cb`。
  与源仅第 16 行 `kLogicalWidth = 32` 改为 `64`，block 仍为 256。
  这是未验收候选，**不是 native64 实验**。
- HIP 7.15.26333；AMD Clang 23.0.0git，LLVM 提交
  `8f497e0992fb7513f7f78a6f6b6f1056c375e961`。
- hipcc：`/home/husrcf/anaconda3/bin/hipcc`。
  单独 `-###` dry-run 所列 clang-23 文件 SHA256：
  `ac5fabcc874b1fd5734845cfa85025b71ccdf00988322f3e26cb7b18f86a8284`。
  该记录含 resource-dir 和 7 个计划链接的 bitcode 哈希；不等于实际进程
  身份核验，也未冻结全部头文件、共享库和 SDK 输入闭包。

## 实际编译结果

两份源码 × 两种 contraction 配置 × IR/汇编，共 **8 次编译，均退出 0**。
每项单独保存命令、stdout/stderr、产物哈希和 driver dry-run；IR 和汇编是
分别从相同源码编译，不声称汇编由保存的 `.ll` 文件直接生成。

| 输入 | 配置 | 源码第 49 行对应的 IR | 对应汇编局部更新 |
| --- | --- | --- | --- |
| logical32 源 | 默认 `-O2` | `fmul contract`、`fadd contract` | `v_fmac_f32_e32 v4, v6, v6` |
| literal64 候选 | 默认 `-O2` | `fmul contract`、`fadd contract` | `v_fmac_f32_e32 v4, v6, v6` |
| logical32 源 | 另加 `-ffp-contract=off` | `fmul`、`fadd`，无 contract | `v_mul_f32_e32` 后 `v_add_f32_e32` |
| literal64 候选 | 另加 `-ffp-contract=off` | `fmul`、`fadd`，无 contract | `v_mul_f32_e32` 后 `v_add_f32_e32` |

定位使用 kernel `_Z22rms_norm_f32_logical32PKfPfif` 内局部循环的 load、
phi 累加器、乘加 use-def 和 debug 位置：输入加载为第 48 行，乘法为第 49
行第 22 列，累加为第 49 行第 13 列；汇编为 `.LBB0_2`。
默认两份汇编第 51 行为 FMAC；off 两份第 51/55 行分别为乘法/加法。
这是人工核对的编译观察，不是新机器码 checker。

LLVM 的 `contract` 允许乘加融合，但不单独授权任意重结合；`reassoc` 是
另一个标志。仅有 contract 不能证明已经融合，本次还核对了实际生成的汇编。
见 [LLVM LangRef](https://llvm.org/docs/LangRef.html#fast-math-flags)。
本次四份 IR 的局部循环均未观察到 reassoc；不据此证明整个后端没有重排。

关闭 contraction 后，第 53 行除法 lowering 附近仍有 FMA 指令。因此不能
按“整份汇编是否出现 FMA”判断第 49 行的收缩行为，更不能声称 off 禁止了
所有用于实现其他操作的 FMA。

四份汇编均记录 `.amdhsa_wavefront_size32 1` / `.wavefront_size: 32`，
`.amdhsa_float_round_mode_32 0`、`.amdhsa_float_denorm_mode_32 3`；16/64 位
对应字段也为 0/3。这里仅报告编译器发出的字段值，**未验证运行时 FP 模式**。
literal64 源码在默认 wave32 下能编译，不证明其 collective 合法或结果正确。

## 复现与工件

源与候选的实际输入副本、脚本、原始报告均在
`artifacts/wb-fp-ir-qZFn37/`；矩阵在 `matrix/`。该目录被忽略，不随 Git 推送。
`matrix/report.json` SHA256：
`fee4e55f93d04a16299c0b4840e2fdf1db112678a2c76e7771247d5044ed563c`。
报告逐项保存 8 个产物哈希；首次探索的 `source.ll` 和日志也保留。

以下从独立输出目录复现单项；`INPUT` 使用上面的固定源或仅单 token 改写的
候选，`OUTPUT` 使用新路径；第二组命令加入 `-ffp-contract=off`。

```bash
hipcc -O2 -gline-tables-only --offload-device-only --offload-arch=gfx1100 \
  -S -emit-llvm INPUT -o OUTPUT.ll
hipcc -O2 -gline-tables-only --offload-device-only --offload-arch=gfx1100 \
  -S INPUT -o OUTPUT.s
```

每条命令另加 `-###` 保存计划工具链，不能把 dry-run 当实际编译。
实际编译均有 `--hip-link` 未使用的 warning，未隐藏该日志。
输出含绝对路径和 debug 元数据，换目录重放不要求产物字节哈希相同。

## 对现有检查的影响

目前不能把默认编译的 `partial += value * value` 解释成严格的两次独立舍入。
另一方面，两侧观察到同样的局部 FMAC，也**没有证明**输入值、执行坐标、FP
环境、归约树、rsqrt、最终输出或机器码整体等价。抽象局部对应的外部解释
假设仍未解除；不升级 `leaf_value_correspondence` 或 `deployable`。

off 仅为诊断对照，不用于事后更改 baseline 或降低验收要求。历史 GPU
baseline 是普通 `hipcc -O2` 链接程序；本轮多了 debug/device-only 编译阶段，
不能反向声称核验了历史可执行文件。下一步需在保持冻结协议的前提下，把
编译选项与工件身份接入验收输入，并继续处理归约值和合法目标执行条件。
