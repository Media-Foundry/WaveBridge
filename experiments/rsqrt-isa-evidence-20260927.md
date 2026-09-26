# 首例 RMSNorm：rsqrt 指令路径、文档精度与条件适用域

日期：2026-09-27；基线提交 `aec70c5`。

本轮是既有编译产物、当前 SDK 文件和官方文档的核验，以及 CPU 上的精确
有理区间计算。没有重新编译、没有 GPU 作业、没有 native64 运行结果。

## 已观察到的编译路径

源文件 `benchmarks/cases/llama-rmsnorm/baseline/rmsnorm_logical32.hip.cpp:53`
调用 `rsqrtf(total/ncols+epsilon)`。已有 O2/gfx1100/default contraction 产物
来自 `artifacts/fp-compile-bi8gy8eo/`；本轮重新计算摘要并读其 IR/汇编。

- 当前 SDK 的 `__clang_hip_math.h:671` 将 `rsqrtf` 转给 `__ocml_rsqrt_f32`。
- OCML bitcode 经 LLVM 反汇编，其正常输入支路使用 `llvm.amdgcn.rsq.f32`。
- 最终 `ir.ll:109` 起，比较归一化分母与 `0x00800000`（最小正规 float32）。
  较小时先乘 `2^24`，执行 rsq 后再乘 `2^12`；否则直接保留 rsq 结果。
- 最终 `assembly.s:255` 为 `v_rsq_f32_e32`，前后有相同含义的缩放与选择。
  该 rsqrt 支路没有观察到 Newton 修正。除法的 rcp/FMA/fixup 序列是另一项
  操作，不能把它的修正步骤误算成 rsqrt 修正。
- 汇编仍记录 wave32。宽度64的显式关系模型不是此汇编已支持 native64 的证据。

| 证据 | SHA256 |
| --- | --- |
| 历史编译 report.json | `5f152c2e8d9f5e3246691c714ab0ed42cf8356703c3268fbeab243db4f31dd72` |
| 历史 ir.ll | `f9bdf8c53f5d13cb0307f75f20047d1de164817f470aa45627b0ba587f2d5e60` |
| 历史 assembly.s | `d21456b4142a37903f934a6c6a8b4e8048c2ab562c93665f712a0a2225de2fae` |
| 当前 SDK ocml.bc | `7b0d1bc455ec41ad461b688f404c211a12b880e36ff74eb8061e97502464bae8` |
| 当前 SDK __clang_hip_math.h | `3a2a401fa4b9a565d9db5a6a5474555942d0f314e0517d51dc69b08707ff3c0a` |

SDK 根为 `/home/husrcf/anaconda3/lib/python3.12/site-packages/_rocm_sdk_core`，
两文件分别位于 `lib/llvm/amdgcn/bitcode/` 和 `lib/llvm/lib/clang/23/include/`。
当前 SDK 文件摘要不是补造历史构建时的依赖快照；历史实际链另有保存的最终
IR/汇编支持。GPT-5.6 Sol 独立只读核对了该路径。

## 官方依据：API 测量表不等于指令全域契约

[HIP 7.15 math API 页面](https://rocm.docs.amd.com/projects/HIP/en/latest/reference/math_api.html)
的 rsqrtf 行列出 `[0.01,100]` 测试范围及 ULP 差异；页首的定义又以 C++ 标准库
结果为比较对象。因此不能从这一行推出本案例全部正 epsilon 范围内的相对
精确实数误差上限，也不能把有限测试统计当作全域证明。

更直接的依据是 [RDNA3 ISA reference，文档70650](https://docs.amd.com/api/khub/documents/UkT_UPQL21KfKAMUBFnZTw/content)，
封面日期 15-August-2023，§16.8、印刷页276（PDF零基页284）。`V_RSQ_F32`
说明给出单 ULP 精度，并指出非正规数刷新。该文件由
[AMD GPUOpen 的官方 RDNA3 发布页](https://gpuopen.com/news/rdna3-isa-guide-now-available/)
链接；网页重定向后的元数据日期不同，不应混写成本文所读PDF的封面日期。

这给出可采用的 **ISA 可信前提**，不证明具体芯片无实现错误。也不自动证明
任意 `rsqrtf` 编译路径均对应该指令。需要分别核对目标架构、实际指令路径、
输入与结果不在特殊值区间、实际运行工件身份。

## 非循环的条件域核验

执行：

```bash
PYTHONPATH=src:. python3 -m experiments.rsqrt_domain_audit
```

脚本读取冻结协议实际 Python 数值边界并记录原始协议哈希，对每个
`ncols=1..1023`、FMA/分离累计、显式 width32/64 模型计算上下界，共4092个
配置。每项均重新调用平方和/路由检查；不读取缓存的成功报告。

它先由已有总和误差界和非负除法/加法律建立 rsqrt 输入区间，不使用 rsqrt
误差界作为前提，所以没有“先假定 rsqrt 正确，再证明其输入适用”的循环。
输入值与 epsilon 在区间上处理，不是随机抽样；列长则完整枚举。

若区间落在 `[2^-20,16]`，精确倒平方根处于 `[1/4,1024]`，非正规数缩放
支路不被选择。根目录 `PROOF_PACKAGE.md` 给出把明确的一 ULP 契约解释转换为
保守 `rho=2^-22` 的证明；该数值不再只是示例中任意指定的假设。

## 本轮实际结果

本轮全域审计完成：4092个配置均进入条件正规域；聚合分母区间约为
`[9.999998807907139e-7, 4.001004530074643]`，精确有理端点保存于报告。
最大上界出现在列长769、分离乘加、显式宽度64模型；这是界最大，不是实测
误差或实际分母最大。工件 `artifacts/wb-rsqrt-domain-yOlR83/` 保存报告、
运行进度和 check/demo 日志；report.json SHA256：
`8da39ee1f0a9a8238946e710a2d0143ada021b9987f37d1b645172f9637a2ea9`。

完整869项CPU测试通过（68.464秒，匹配native插件启用，无跳过），demo及
diff检查通过。3项新增回归覆盖域端点/两种模式、非法参数和tiny epsilon
不被提升为正规域。独立复核未发现条件区间与ULP推导的阻断问题。

## 仍未建立

- 显式模型到所有源/目标执行指令的完整对应与实际运行工件绑定。
- 本地平方、加法、除法、转换、最终乘法的实际误差律全部适用。
- 冻结 float64 reference 自身的舍入误差和实际容限验收。
- native64 的通信、参与、运行支持及 GPU 候选放行。

因此报告保留 `rsqrt_contract_verified=false`、`numeric_contract_checked=false`
和 `deployable=false`；区间 checked 仅陈述已检查的条件模型域。下一步可将
已明确的 ISA 前提与真实编译后缀对应连接，而不是继续凭函数名选误差常数。
