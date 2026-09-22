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

### 条件 unsigned compound 列递推

`verification.column_coverage.check_unsigned_compound_interval` 只处理外部给定的
相同位宽 signed/unsigned int、固定正 block 宽度 B、起点 `0..B-1`、步长 B 和
非负 signed 列数区间。它必须检查 unsigned 起点到 int、int 到 unsigned 的
转换、unsigned 加法及赋回 int 的值保持，包括最后一次有效迭代后的增量。
只有这些条件成立，才能将机器递推对应到既有无溢出的列覆盖模型；不是断言
源程序实际执行 signed 加法。超出支持位宽/范围或可能发生 wrap/赋回改变保持
unknown，不依据语言版本猜测超范围 signed 转换结果。

检查不验证 AST、getter、launch 或循环体，不从 `blockDim.x` 名字推断 B。
checked 只描述该条件递推及覆盖模型，不能据此将源码 unknown 升为 recovered，
也不能作为候选部署许可。实际源码表达式与这些外部参数的连接需另行检查。

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

`receiver_evaluation_observation` 独立观察同 root 中唯一的 receiver VarDecl：
只支持无 initializer 的 extern、非 TLS、非 reference、非 volatile 对象；四处
类型证据须解糖后一致，别名证据缺失保持 unknown。声明 children 只允许空或
CUDADeviceAttr/WeakAttr；属性不提供副作用保证。observed 仅在对象已初始化、
生命周期有效且扩展遵循 static-member discarded-object 求值规则的前提下，
描述 receiver 本次求值不读写内存。不修改旧 link 状态或 receiver_purity。

依据：[成员访问](https://eel.is/c++draft/expr.ref)仍求值对象表达式，
[discarded-value 规则](https://eel.is/c++draft/expr.context)不对该非 volatile
glvalue 施加 lvalue-to-rvalue 转换；这不是忽略任意 receiver 副作用的理由。

## Getter 返回域检查：`getter-return-domain-check/v1`

显式`getter-leaf-domain/v1`绑定同AST中的外部函数ID、常量实参、返回类型与
闭区间。checker从原始函数体独立遍历受限getter链，检查逐级整数转换在整个
声明区间上值保持；不根据函数名认定坐标。返回窄化可rejected；前提不匹配或
不支持则unknown。checked仅描述该条件值保持性质，不能扩展为外部函数实现、
线程坐标语义、真实launch或整核等价的保证。详见 `compiler/verification/README.md`。

对 `BuiltinFnToFnPtr` 仅支持直接 `CallExpr` callee 位置的零参外部叶：
单个 prvalue `<builtin fn type>` DeclRefExpr 精确指向唯一 FunctionDecl，
必须与叶协议 ID 相同，带 BuiltinAttr，声明/ref/cast 的零参整数函数签名一致
（`R ()` 或 `R () noexcept` 对应指针类型）。其它 callee、嵌套求值、指针
间接调用及有参 builtin 仍 unknown；普通函数的既有 literal 实参支持不变。
BuiltinAttr 只核对 AST 表示，不证明该叶无写或其坐标含义。返回值转换仍须
通过值域检查，无写结论仍要求单独 effect 协议。此转换的调用位置约束依据
[LLVM 17 定义](https://github.com/llvm/llvm-project/blob/llvmorg-17.0.6/clang/include/clang/AST/OperationKinds.def#L320-L322)，
并以真实 CUDA device-only AST 回归；不把源码 builtin 身份升级为机器码保证。

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

`coordinate-column-header-observation/v1` 的 observed 仅表示受限直接属性起点和
unsigned compound increment 的结构及 getter/receiver 绑定已观察到；不表示
这些 getter 具有 CUDA/HIP 坐标语义。它不填写数值步长，也不建立 header
递推，父循环继续 unknown。body 保持标志由原受限副作用检查独立建立，依赖
源有效性和无别名前提；不证明正常完成、贡献或参与。必须另行检查 launch、ABI、整数转换/加法和循环体
保持性，不能将该观察替代下述列域门槛。原始初始化和增量 AST 保留在父报告中。

循环报告将`header_recurrence_observed`与`body_preserves_induction`、
`body_preserves_bound`分开。后两项只有在受支持的副作用子集中完成检查才为
`established_in_supported_effect_subset`；仅观察循环头不允许进入列域checker。
允许的存储目标为直接非保护变量及简单数组下标；引用转换、逗号等复杂写入
目标和未支持节点（包括汇编）返回unknown。数组写入仍依赖不与受保护标量
别名的显式前提；这不是任意C++别名分析，也不证明循环体内存访问有效。

声明类型的引用性质取自可信Clang声明的desugaredQualType，缺少别名展开证据
不得按值存储放行；同一分类用于引用绑定及写入目标。仅支持自动存储期的
induction，static/thread_local返回unknown。普通值类型别名不等于引用，
但循环头类型别名的支持范围不随此修复扩大。

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

`conditional-entry-loop-check/v1`按同AST调用和loop范围连接fresh列域报告，给出
逐线程有限递推次数上界与最后增量安全性。仍依赖每次循环体正常完成和上游全部
前提，不能用该条件结论反过来证明线程到达循环。调用正常返回、内存有效性和
participation继续未建立，不授权GPU部署。

`getter-completion-assumptions/v1`按root hash和kernel ID绑定前缀getter的外部叶
域协议，并显式声明外部正常返回假设。`conditional-entry-call-check/v1`仅组合
这些假设下callee body的有限返回链，不证明外部终止、调用点求值或整体到达。
缺协议或值保持拒绝使组合unknown，不把数值反例误报为不终止反例。

`grid-domain-assumptions/v1`绑定root/kernel/launch、第0配置位置与字段轴协议。
`conditional-grid-domain-check/v1`从fresh host guard和构造式检查一维正grid域，
不把必要条件过近似当可达集合。用它推导block-id域还需要外部API语义，不能因
字段或函数名叫x/group便自动建立该含义。

`row-coordinate-assumptions/v1`显式连接group-id叶API、轴0及grid绑定。
`conditional-row-coordinate-check/v1`从同AST恢复row声明与初始化链并核对整数
值保持，给出条件行坐标域。它仅覆盖初始化式，不证明row*ncols算术、指针范围
或每次launch的精确row/nrows相关性；不授权部署。

## Getter 的条件无写协议

`getter-no-memory-write-check/v1` 首先 fresh 执行现有 getter 返回值域检查；因此
它要求有依据的外部叶值域和整数 ABI，不是独立于值域的 effect 分析。值域拒绝
只使该充分检查 unknown，不表示确实发生写入。不得为通过此检查虚构值域。

`getter-leaf-effect-assumption/v1` 必须提供 `root_sha256`、
`start_declaration_id`、`external_leaf_declaration_id` 的精确绑定，
`external_leaf_no_memory_write_assumed` 与
`valid_calls_and_external_leaf_returns_normally_assumed` 必须严格为 true，
并提供非空 `evidence_reference`。引用不自动读取或核验，报告明确 unverified。
成功只说明：在这些前提下，受限单 return wrapper 调用链不写内存。函数名、
BuiltinAttr、ConstAttr 均不能替代协议；receiver/调用点求值、坐标语义、机器码
及整核内存行为不在范围内。该入口尚未用于放行 column_loops 的 body。

两个 getter 检查入口允许显式 `max_ast_nodes`：默认仍为 1,000,000，必须为
1 至 10,000,000 的整数（不接受布尔值），有效值记录在值域报告的 budget 中。
这只是完整 TU 声明扫描的资源预算，不放宽语义、声明唯一性或调用深度；扫描不因
找到目标而提前结束，超限仍 unknown。AST 解析及规范化哈希在节点扫描之前，
因此该参数不是总内存/墙钟时间上限；大型输入须由调用者另行限制资源。
无写入口只复用本次 fresh 值域检查生成的 root 哈希，不消费外部旧报告。

`check_property_no_memory_write` 从完整 root 按 ID 唯一选择原始 PseudoObjectExpr，
fresh 运行 value link 与 getter effect 检查，再按 ABI 检查 property/getter 返回类型
一致。不接受调用者自报分析结果或脱离 root 的 AST 片段。receiver 必须有上述
observed 结构及 exact no-read/write 含义；不能把任意 observed 当成无副作用。

外部 `property-receiver-assumptions/v1` 精确绑定 `root_sha256`、`expression_id`、
`receiver_id`、`receiver_declaration_id`、`call_id`、`callee_declaration_id`。
`receiver_initialized_and_alive_assumed`、`extension_static_member_evaluation_assumed`
必须严格为 true，并有非空 `evidence_reference`（只记录为 unverified）。
`property-no-memory-write-check/v1` 的 checked 仅表示在这些前提及 getter 外部
前提下，该属性表达式无写；不涵盖外围 cast/body、初始化历史、实际坐标或 launch。
selector/link/getter 分别遍历 TU，节点预算不是组合总内存或时间上限。

## 行偏移整数关系

`row-offset-check/v1`消费完整表达式、精确row/count声明ID、非负闭区间及显式
整数ABI。受限乘法表达式规范化为系数和两个变量的幂次，必须恰为`row * count`；
范围碰巧相同不算关系相同。各节点须可表示，整数转换须全域值保持。乘法可能
溢出为unknown；符号关系不符或转换不能全域值保持为rejected。这些拒绝描述
给定条件域/关系，不证明某个错误输入实际可达；报告counterexample为局部诊断。
支持声明读取、非负字面量、prvalue括号、受限整数转换和乘法；最多128节点、
深度32。typedef依desugaredQualType查询显式ABI，不按int64_t名字猜位宽。

`conditional-row-offset-check/v1`从同一原始AST fresh检查row、thread和列数域，
按选定kernel/launch及精确声明ID连接前缀两处完整offset_ast，再独立检查。
checked只表示两处指针更新的整数RHS关系及无溢出；矩形域可能过近似真实组合。
它不检查指针加法、分配范围、别名、数据访问、线程参与或浮点结果，不授权部署。
