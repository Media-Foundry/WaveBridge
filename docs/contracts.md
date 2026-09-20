# 模型、检查与证据协议

## 当前模型：`qdot-model/v1`

示例见 `examples/qdot/source.json`。字段必须齐全；未知字段、重复 JSON 字段、布尔值冒充整数、非法版本和非正尺寸均被拒绝。输入文件上限 64 KiB。

| 字段 | 语义 |
| --- | --- |
| `domain.rows / columns` | 同一次关系检查的固定合法形状；所有输入元素可为任意数学整数 |
| `numeric_contract` | 当前仅 `integer_exact_unbounded` 可获得 `checked` |
| `launch.block_threads / grid_blocks` | 与 kernel 一同检查的 launch；不读取设备默认值 |
| `kernel.cooperation_width` | row/group 与 lane 的划分，限逻辑 32 或 64 |
| `kernel.column_stride` | 每线程列循环步长；与宽度分开存储，以暴露不一致 |
| `kernel.quantization_group` | scale 数据格式；不是执行宽度 |
| `kernel.reduction_width` | guarded shuffle 路由分组宽度；与计算对象分开存储 |
| `kernel.reduction_offsets` | 按顺序执行的同步 shuffle-down 加法阶段 |
| `kernel.writer_lane` | 每个计算组的输出写入者 |

线程 `t` 属于 `row = block * (block_threads / cooperation_width) + floor(t / cooperation_width)`，组内编号为 `t % cooperation_width`。局部累加遍历 `column = lane + k * column_stride < columns`。

每个初始贡献为 `q[row,column] * scale[row,floor(column/quantization_group)] * x[column]`。一个 shuffle 阶段从上一阶段的快照取值；只有 `t % reduction_width + offset < reduction_width` 时才相加。该语义是本项目显式定义的 guarded 模型，不代表所有 CUDA/HIP intrinsic 的默认行为。

关系检查将每个输出规范化为带整数系数的单项式集合。系数保留重复计数；行、列和 scale 下标保留数据依赖。检查源/目标的每个输出多项式是否相同。它检查源/目标关系，不证明源模型符合作者想实现的数学函数。

## 结果语义

| 结果 | 含义 | 编排行为 |
| --- | --- | --- |
| `checked` | 在报告记录的固定形状与无界整数模型内，全部输出多项式相同 | 仅接受模型候选 |
| `rejected` | 在支持的模型内发现输出差异，或目标模型存在缺失写入等错误 | 拒绝候选 |
| `unknown` | 前提未建立、契约不一致、collective 读取 inactive lane、语义不支持或资源上限 | 拒绝适配，不猜测结果 |
| `input_error` | CLI 无法加载合法结构化输入 | 不生成检查结论 |

数值契约不支持时不能降级到随机输入后签发 `checked`。源模型无有效覆盖时只能说前提未建立；不能把有缺陷的源程序解释为正确参考。

默认上限为 64 行、4096 列、每块 256 线程、64 个块和 2,000,000 的保守符号展开预算。限制在报告中记录；增加预算只能改变可检查规模，不能扩大语义范围。

报告包含源/目标规范化模型 SHA-256、checker 版本、固定域、数值契约、预算、诊断和未证明事项。当前没有持久化缓存。未来缓存必须额外绑定实际源码、编译选项、目标能力、全部外部假设及 checker 二进制/代码版本，不能仅按 kernel 名称复用。

## 未来编译器工件

以下是接口需求，不是当前已实现的 JSON schema：

- `SourceBundle`：源文件集合及哈希、入口、编译数据库、宏和 include 依赖、源 launch、源执行语义。
- `ExternalContract`：合法输入域、shape/stride、别名约束、数值关系、溢出规则、源有效性依据。
- `RelationArtifact`：数据/运算/路由/掩码/存储/输出关系、推导来源、适用条件和拒绝原因。
- `CandidateBundle`：候选 kernel 与 launch、目标能力要求、生成器版本、父工件哈希。
- `CheckEvidence`：检查器版本、证明义务及逐项结果、反例或未知原因、保证范围、绑定哈希。
- `ExecutionEvidence`：目标编译、实际波宽、数值测试、运行时检查、性能原始样本及有效性状态。

相等性、容差通过、运行时合法性和性能是四种独立证据，不能合成一个没有范围的 `verified: true`。

## XOR 路由依赖检查：`xor-route-check/v1`

`verification/xor_routes.py` 独立枚举2～64个lane（2的幂）、最多16个阶段。
假定全参与logical group，每阶段按 `lane XOR offset` 从上一阶段快照取值再加到
本lane。每lane初始持有一个不同贡献，检查结束时每个输出是否恰好含每个输入一次，
计数保留重复贡献；缺阶段和重复阶段均可被拒绝。

这里的 `checked` **只检查该有限路由模型的覆盖与重复度**，不是对真实源程序、
浮点加法结果、收敛、mask或物理wave语义的保证。不同stage顺序可有相同贡献计数，
却不保证浮点结果相同。源码恢复器的外部shuffle声明选择仍需独立语义依据；
绑定某个函数ID不能自动证明它就是XOR shuffle。所有结果均不可直接部署。

## 共享 partial 的两阶段贡献检查

`verification/block_routes.py` 在上述XOR快照假设下，模拟每组归约、单writer
写共享partial、barrier之后按lane读取partial（其它lane注入零）、再次组内归约。
逐输出线程检查是否恰好包含全block每个初始贡献一次；记录缺失或重复反例。
上限为1024线程、64lane逻辑组和每次16阶段，partial组数不得超过逻辑宽度。

这是条件模型，不证明源码坐标相等、源launch使用的block大小、实际shared容量、
barrier可达性或浮点值。缺少barrier前提返回unknown；模型内未写入的partial
读取、容量不足、缺失或重复贡献返回rejected。不能把model checked升级为
完整源/目标kernel验证。恢复器与此checker实现依赖分离。

## 相同步长的列覆盖检查

`verification.column_coverage.check(columns, starts, stride, int_bits=32)`
检查每个给定起点的 `i < columns; i += stride` 非负递推，是否将
`[0, columns)` 的每列覆盖且仅覆盖一次。相同步长的序列按余数分类；每个
必需余数必须从最小非负代表开始，两个同余且非空的序列必然重叠。
只排序最多1024个线程的余数，不按列数展开，时间为 O(T log T)。

位宽、列数、起点和步长必须在支持域内；最后一次有效迭代之后的增量也检查
signed overflow，发生溢出时返回 unknown。模型内遗漏和重复返回 rejected。
这里的 checked 仅表示给定递推的列覆盖，不证明源码线程坐标、每次迭代的
贡献运算、输入别名、输出归属或浮点等价；调用者不能把它升级为源码保证。
