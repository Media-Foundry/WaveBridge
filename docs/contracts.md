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

四参数调用的受限恢复额外保留全32位掩码原始 AST 与参与/收敛外部前提。
当前 checker 本身仍不建模掩码；只有 width32、显式 unsigned int 全掩码的
受支持结构才能进入相同条件模型，部分或动态 mask 保持 unknown，不能删除
mask 后套用原保证。原三参数逻辑宽度支持范围不因此改变。

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

## 整数转换的区间值保持检查

`verification.integer_conversion.check_interval` 接收闭区间、源/目标位宽与
signedness，只检查区间内所有整数是否都能由两个类型表示。源域不合法或
参数不支持返回unknown；源域合法但目标范围不足返回rejected并给出端点反例。
checked以外部声明的值域与类型信息为前提，不自行从类型名或源码猜测ABI，
不检查表达式求值、浮点转换、指针或完整源程序。编译器预定义宏记录与实际
源码/目标配置的绑定仍需单独核对，不能以一次空TU宏探测替代全部前提。

## host 守卫区间：`launch-guards/v1`

受限 AST 分析输出 `intervals`、`guards` 与 `skipped_guards`，按精确声明 ID
关联 launch 前的顶层提前返回条件。区间是执行到指定 launch 的必要条件，
不是外部输入契约或 host 可达性证明。未支持的普通守卫不贡献约束；跳转绕过、
变量非只读使用或不支持控制流阻止恢复。详见 `compiler/analysis/README.md`。
此报告不由独立 checker 签发，始终保留 `checked=false`、`deployable=false`；
整型位宽和源有效性仍是显式前提。

## 构造字段域检查：`constructor-values-check/v2`

显式声明闭区间可以作为符号构造实参的条件域；checker按精确声明和类型关联
输入，复用整数区间检查验证整段经过实参与字段初始化转换后仍值保持。
`value_kind=interval` 不携带单一 `value`。只有显式传入区间表时使用v2；
默认常量接口仍为v1。区间真实性和源guard语义没有被此checker独立验证。

CLI 的 `--use-host-guard-assumptions` 必须显式开启，输出配置域报告v2并记录
前提门控和输入/实现哈希。结果不授权部署；详见 `compiler/verification/README.md`。

## kernel 实参域：`kernel-argument-domain-check/v1`

单个位置绑定条目、显式声明闭区间和整数ABI是输入。checker直接读取实参AST
的允许转换链，并验证其到形参类型的值保持；位置绑定正确性仍是外部前提，
不独立核对整个kernel签名。报告区分常量和区间，保存参数/声明ID、位置、转换
与输入hash。指针、浮点、调用和未知域不支持；其它参数不会因某个参数checked
而被放行。所有结果都保留 `source_program_checked=false`、`deployable=false`。

## 条件共享内存容量

`shared-byte-expression-check/v1`在显式integer_types与sizeof_bytes表下求有限
非负字节表达式，逐节点检查整数范围与转换值保持，深度/节点预算超限保持unknown。
`shared-capacity-check/v1`将该字节数或静态数组声明extent与受限块归约模型需求
比较：不足为rejected，足够为checked，不支持或前提缺失为unknown。

该checked以前述结构恢复准确、同AST绑定、实际block/坐标符合模型、单数组偏移0、
无其它动态shared分配及显式ABI匹配为前提，不验证源程序有效性或运行时内存安全。
CLI `conditional-shared-capacity-check/v1`保存源报告、ABI与实现哈希，所有已报告
launch均checked且没有未解析launch才可整体checked；不签发部署结论。

## 显式轴绑定下的block配置

`block-configuration-check/v1`绑定一个launch与恢复链的kernel ID，按显式FieldDecl
ID→x/y/z映射解释独立构造字段检查结果，并要求(x,y,z)=(block_threads,1,1)。
与仅检查维度乘积不同，轴交换和非一维布局会拒绝。缺轴绑定、常量或ABI为unknown。
轴/API对应、源报告真实性、源码线程坐标含义及实际执行配置仍为外部前提；
source_program_checked/deployable始终false，不能用它单独放行候选。

## 初始化结果调用连接：`initializer-value-link/v1`

在输入为真实、单TU、符合Clang pseudo-object结果不变量的AST前提下，连接
初始化式到结果调用及保留的外层整数转换链。它不是整数转换checker，也不赋予
外部调用坐标语义。`recovered`不得转换成`checked`或部署许可；数值值保持、
receiver上下文有效性、外部函数/轴语义和launch域须另行建立。具体支持子集与
不变量来源见 `compiler/analysis/README.md`。

## Getter 返回域检查：`getter-return-domain-check/v1`

显式`getter-leaf-domain/v1`绑定同AST中的外部函数ID、常量实参、返回类型与
闭区间。checker从原始函数体独立遍历受限getter链，检查逐级整数转换在整个
声明区间上值保持；不根据函数名认定坐标。返回窄化可rejected；前提不匹配或
不支持则unknown。checked仅描述该条件值保持性质，不能扩展为外部函数实现、
线程坐标语义、真实launch或整核等价的保证。详见 `compiler/verification/README.md`。

## 条件线程起点组合

`initializer-domain-check/v1`检查可信value_link及getter证据的ID/ABI/类型连接，
并逐级核对初始化整数转换；本身不重新验证前端恢复。
`conditional-thread-start-check/v1`组合入口则从同一原始AST重新运行前端与三类
checker。外部`thread-start-assumptions/v1`绑定root hash、kernel、选定launch、
轴字段映射和local-id接口语义。满足全部门槛才可条件性确认该launch下列起点
等于local x及其区间；原始AST可信性、外部API真实性和实际运行配置仍是前提。
不授权GPU部署，不扩大到其它坐标读取、其它launch或完整kernel正确性。

## 条件索引分解

`index-partition-check/v1`在显式坐标锚点等于local_x和宽度常量绑定前提下，
检查完整表达式在每个线程上的除法/余数关系及整数值保持。区间输出只是摘要，
成功依据是逐点相等。`conditional-block-coordinate-check/v1`将同AST的真实线程
起点证据、helper源码恢复、两个getter/坐标转换与该checker连接；外部local-id
协议、ABI、源码有效性和实际运行配置继续显式保留。结论只覆盖group/lane
初始化式，不自动解除路由、同步、其它表达式转换或整核数值正确性义务。

## 条件列数域覆盖

`column-coverage-interval/v1`在固定starts/stride与signed递推语义下，将上界的
索引覆盖和末增量安全性推广到整个闭区间，保留完整upper_check及域内拒绝反例。
`conditional-column-domain-check/v1`将同AST线程证据与新恢复的launch列数实参、
host guard必要条件域连接，显式启用host假设后才可能checked。只读形参、直接
kernel循环与共同起点/步长是支持边界。它检查索引生成次数而非数据贡献次数；
不证明区间可达性、所有线程参与、内存安全或数值等价，不授权GPU部署。

## 共享阶段整数关系

`conditional-shared-index-check/v1`重新检查同AST的helper坐标，并检查完整写入/
收集谓词及活跃线程下标表达式；结论只覆盖整数关系，不将数组下标模型升级为
真实shared读写安全或同步保证。所有坐标、ABI、有效执行与参与条件仍显式保留。

`conditional-shared-storage-check/v1`进一步fresh恢复同AST调用链、数组绑定和
选定launch，核对已检查helper/shared形参/线程模型一致后比较容量。整数下标与
容量两项条件结论绑定到同一数组，不自动证明动态shared独占布局、别名、同步或
整体内存安全；单数组偏移0、实际配置及ABI仍为前提，不签发部署许可。

## 入口控制义务

`entry-control-obligations/v1`仅恢复kernel入口至首次精确helper调用的受限控制
结构及未解除的调用/循环义务。它不签发参与或收敛结论；早退等不支持前缀为
unknown，局部归约结构仍可独立recovered。未来参与checker必须消费并解除这些
义务，不得将结构恢复或前缀中没有If直接当作所有线程到达的证明。
