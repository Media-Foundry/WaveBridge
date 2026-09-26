# 32/64 两阶段归约的有限舍入见证

基线 `d9201d4`，2026-09-26。此项是**显式路由模型的诊断**，不是源码自动
恢复、HIP 实际执行或完整数值协议证明。没有新增 GPU 作业。

## 具体问题与结果

已有 block-route 检查能够确认两种布局的贡献集合相同，但有序加法 DAG 不同。
这不意味着每个输入的结果都不同，也不能推导逐位等价。本次固定一个能让
舍入区别实际出现的输入，防止后续组合检查错误地把贡献计数当作 FP 保证。

输入为一行 34 列，`x[0]=1`、`x[1]=x[33]=2^-12`，其他元素为正零，
epsilon 为 1e-5。现有冻结协议的 validate 接受该输入。block=256、stride=256，
每个活动线程只有一个输入，因此局部平方和的非零叶为：

| block-local thread | 非零局部叶值 |
| --- | --- |
| 0 | 1 |
| 1、33 | 2^-24 |

这些平方和零初值加法均精确；在此见证中，局部是否发生乘加融合不是差异来源。
两边采用全参与、快照 XOR-add、降序 offset、每组 lane0 写共享 partial，
随后每组前 block/width 个 lane 加载 partial、其余填正零，再执行 XOR 归约。
这些是显式模型前提，不是本轮新证明的真实 intrinsic/同步性质。

按每次加法 round-to-nearest ties-to-even 的 binary32 模型：

| 布局 | 最终归约总和 | 位模式 |
| --- | --- | --- |
| width32 | 1 | 0x3f800000 |
| width64 | 1 + 2^-23 | 0x3f800001 |

整数模型的全部 256 个输出线程均呈上述差异，每个配置内部结果一致。width32
先将 lane0 的 1 与 lane1 的半 ULP 合并，ties-to-even 舍去；第二阶段再加
lane33 所在组的半 ULP，再次舍去。width64 的 offset32 先将 lane1 和 lane33
合成一个 ULP，最后与 1 相加，保留该 ULP。

## 复现和独立性

```bash
PYTHONPATH=src python3 experiments/reduction_rounding_witness.py
PYTHONPATH=src python3 -m unittest tests.test_block_route_rounding -v
```

脚本使用整数表示 2^-149 的倍数，精确相加后按 24 位有效数执行 ties-to-even，
不依赖宿主 Python float 的逐次舍入。有限非负域外与溢出拒绝；只模拟固定两种
路由，不作为一般 IEEE 浮点模拟器。已有 block_routes.compare 另行重查贡献
计数和有序 DAG；没有给现有 checker 新增浮点放行能力。

测试覆盖 ties-to-even、进位、次正规边界、错误输入、修改路由拒绝、精确整数
正例、冻结输入域以及上述不同结果。新测试不是实际 HIP 源码恢复回归。
本地产物位于 `artifacts/wb-rounding-witness-yHNsYH/`（不随 Git 推送）。
GPT-5.6 Sol 另用 C++ float 快照实现独立复核，CPU 使用
`g++ -std=c++20 -O0 -fno-fast-math -ffp-contract=off`；编译和执行不调用 GPU。

## 结论边界与下一步

此见证否定的是**在声明的加法模型下，这两个路由对所有合法行都逐位相同**。
不能据此宣布真实 native64 kernel 出错：其执行模式、通信、FP lowering 和
源程序对应前提仍需建立。也没有评价 rsqrt 或最终输出，不能宣布违反冻结
atol/rtol；同样不证明整个域都在容限内。

后续应把局部求和、不同归约树、除法/rsqrt 与最终乘法分别纳入声明过的数值
契约检查，或选择保持运算树的合法候选。不能放宽容限来消除这个义务，也
不因该见证否定 native64 优化本身。现有 abstract-local-values 结论只到局部
accumulator，其 scope 无需改变；整体 floating_point_equivalence 继续未建立。
