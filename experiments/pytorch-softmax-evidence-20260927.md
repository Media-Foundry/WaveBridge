# 新 softmax target 的冻结分析结果

固定版本与范围见[预运行协议](../benchmarks/intake/pytorch-softmax-protocol.md)，
机器可读索引见[结果](../benchmarks/intake/pytorch-softmax-result.json)。
本轮没有修改任何`src/wavebridge`分析器文件，没有GPU执行或数值验收。

## 输入和实际执行

PyTorch v2.5.1固定提交的persistent softmax头文件与缓存wheel字节一致。
使用真实CUDA/Torch headers加公开harness，实例化原dispatch；仅前置声明
外部`at::cuda::warp_size()`，不赋予返回值，未改变kernel、helper或intrinsic。
原dispatch实例化11个长度，但评估只选运行前规定的float、log2_elements=7、
非masked/nonlog实例，独立target分母为1，不统计为11个case。

```bash
PYTHONPATH=src python3 -m experiments.pytorch_softmax_intake \
  --config artifacts/wb-pytorch-softmax-KhwXBa/config.json \
  --output-dir artifacts/wb-pytorch-softmax-KhwXBa/attempt-02
```

可移植配置格式见`benchmarks/intake/pytorch-softmax-config.example.json`；从repo
根目录执行，按本机真实SDK路径修改并另存配置。示例不自动下载依赖，也不声称
与原始配置文件哈希相同。driver要求源码分析器仍匹配冻结git提交，并记录全体
Python分析实现哈希；后续修改分析器后应建立新的开发评估，不能伪装旧冻结。

Clang 17 CUDA device-only sm80采集成功，518个同次依赖文件被观测；实际编译
依赖中包含相同摘要的目标header。完整的是harness TU AST（约232MiB），不是
生产`SoftMax.cu`；同次依赖观测也不是不可变SDK快照。没有NVIDIA或AMD设备执行。

## 观察到的能力边界

| 层 | 结果 | 解释 |
| --- | --- | --- |
| 入口 | 精确模板实例唯一 | 通过AST模板实参选择，不根据分析成功率选点 |
| 列循环恢复 | 8/8 unknown，0 recovered | 首拒绝均为`bound_not_parameter_or_resolved_const` |
| 归约发现 | 13个可达函数；2次候选尝试，0候选 | 12个未解析调用；遍历预算完成不等于语义分析完成 |
| launch发现 | 1个语法site及4个配置表达式 | 外部warp_size/query/stream和host计算的语义值未建立 |
| 适配、数值或部署 | 未运行/未建立 | 不能填有效接受率、错误放行率或性能 |

这里的1个launch只计选定target；全harness另有10个其他kernel launch出现和
22个未解析launch出现，完整报告保留它们，不声称全TU launch已恢复。

对保存AST追加的独立诊断调用现有integer_constants.evaluate：
`next_power_of_two`的`<<`得到unsupported_binary_operator；`WARP_SIZE`与
`WARP_BATCH`的条件表达式得到unsupported_expression_kind；`WARP_ITERATIONS`
虽顶层是除法，也因依赖上述移位表达式失败，不能误记为“不支持除法”。
这解释了当前循环边界恢复为什么停住，不证明解决常量求值后其余义务就会通过。
多维寄存器数组、functor max/add、masked分支、exp/log等仍超出现有归约子集。

## 首次与重放证据

首次attempt-01在选点/源码/分析器冻结下运行；原始报告SHA256：
`ddc2f32eec58354cdf15b4093646e776b0379bc2870075de43026c9d2a0ca808`。
审查发现评估driver未将自身/config/protocol全部纳入结束复核，故仅加强证据
绑定后重放attempt-02，未修改分析器、harness或上游header，结果相同。
首次原件保留，不能将重放伪装成两份独立验证。

attempt-02报告SHA256：
`3a39162609eddcdd6a144749bc59b1e3fa895d7fe144cef7f7ef8d3db728d5cc`。
其实现、header、harness、driver、config及protocol前后摘要均一致，实际header
依赖绑定通过。原始AST、工具/依赖/命令日志及独立常量诊断保存在
`artifacts/wb-pytorch-softmax-KhwXBa/`；本地大工件未随git上传。

这不是源码错误、不是Polygeist/CKTI失败，也不是G2留出通过。PyTorch依赖树
此前已暴露，未建立严格谱系隔离。本target后续若用于修复，按开发反馈处理。
下一项有依据的通用增量是受限整数移位/条件常量求值，仍需溢出、转换、条件
短路和不支持表达式负例；不能直接读取某个constexpr名字填入32/64。

最终验收：10项新增driver fixture测试通过；完整903项CPU测试通过（65.559秒，
匹配native capture插件启用，无跳过），make demo与diff检查通过。上述单元
测试验证选点、冻结、状态分类与输入变更拒绝，不替代真实Clang记录。
