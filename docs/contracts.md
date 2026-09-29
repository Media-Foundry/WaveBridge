# 模型、检查与证据协议

## 同次原生枚举类型观测

native envelope可包含enum_types与ast_int_bits。前者记录被访问的完整、非依赖
上下文枚举定义：精确EnumDecl/EnumConstantDecl ID、fixed/scoped、canonical
underlying type、Clang存储的promotion type、各自位宽/符号及named constant
十进制值。ID只在同次嵌入AST内有效；旧插件缺少这些可选字段不代表空集合。
coverage非穷尽，常量列表不等于运行时表达式值域。Clang可为scoped enum填写
promotion字段，该字段存在不表示语言允许其隐式转换。
这些是可信编译器观测，不是独立类型定理、运行库API保证或整核检查；消费方
必须fresh绑定同AST精确声明和具体转换，不能仅按类型拼写或跨TU ID连接。

`normal_return_guard.check_enum_binding(payload, function_id)`重新检查嵌入AST的
guard，再由精确参数的typeAliasDeclId穿过直接typedef/alias（至多一层
ElaboratedType）连接EnumDecl。guard常量必须属于该枚举；native记录唯一，
常量ID列表与声明直接成员逐项相同。当前仅接受int/unsigned int底层、同宽
signed int提升观测和非scoped枚举，不扩展任意类型别名或转换支持。
`checked`仅描述这一声明/观测对应。输出保留fresh guard报告、实际转换ID、
payload与选点hash；元数据属于可信前端前提，不是独立类型验证。常量列表
不用于推导runtime域，未反推enum相等，API成功/source/deploy均保持false。

## 显式转换协议下的守卫相等关系

`normal_return_guard.check_enum_equality`重新执行上述绑定，不接受成功报告。
调用者必须提供`enum-bitpattern-contract/v1`：精确payload哈希、function/
parameter/constant/enum ID、有序两个转换ID、相同位宽，以及全域保位、
enum/int按全部位比较、无padding/trap且唯一two's-complement解释的明确前提。
字段必须精确匹配，额外成功结论、单点探针、截断模型均不能替代协议。

独立`integer_conversion.check_bitpattern_equality`在完整W-bit域上检查身份映射
的相等反射，不把signed解释前后的数值保持作为结论，不枚举2^32个值。
组合仅得到：正常返回时，在外部表示/转换前提成立的条件下，参数与常量的
enum值相等。字段`conditional_enum_equality_under_external_lowering_assumption`
显式保留条件，`actual_lowering_verified`和`conversion_contract_verified`仍false。
没有默认协议或按编译器名称自动启用；API成功/输出效果/source/deploy仍false。

`check_call_enum_equality(payload, call_id, conversion_contract)`进一步fresh执行
`check_call`和`check_enum_equality`。核对同root、parameter/constant/转换ID后，
只把相等关系连接到被选中的这一次query调用返回值，不是后续重求值。
报告绑定query call及声明、wrapper call及定义，合并两侧全部假设，保留两个
子报告。字段`conditional_query_enum_equality_under_external_lowering_assumption`
仍为条件性结论；actual_lowering/contract/API/output/linkage/source/deploy
均未验证，正常返回也未被证明。常量的名字不用于决定API语义。

## 查询后置状态到字段快照

`field_snapshot.check_query_output`在同payload中fresh组合地址/字段对象对应与
query枚举相等。核对root、call/decl、wrapper/parameter/constant/cast和完整
实参表后，才消费`query-field-output-contract/v1`。协议精确绑定payload、
getter/query/wrapper、输出位置/address/formal/object/field/read、status常量
及完整有序实参身份；缺项、多项和错误绑定均unknown。

输出协议是外部假设：返回指定状态时，完成调用后的字段含API初始化的确定
plain int；所有实参求值、alias/layout/alignment、对象有效性和API前提成立；
字段及生命周期保持至指定读取（含callbacks/retained aliases）；链接实现遵守
该协议。“曾经写过”不足以替代这个后置状态，也不按函数或常量名推断语义。

在保留的到达suffix/正常执行前提下，紧邻顶层wrapper语句已经正常完成。
父报告将稳定义务ID `field_read_validity`标记为由外部API协议条件性供应，
不在父假设中循环要求同一字段已经可读；child仍保留原始义务。
counter增量有定义、global存储不同、无异步干扰等前提继续保留。
`conditional_output_to_return_relation`只是getter返回该次query后置字段值；
不提供数值域/设备波宽。API协议、实际输出、生命周期、链接/lowering均未
验证，source/deploy false，不能仅凭status checked放行。

`field_snapshot.check_query_initializer`进一步连接一个精确局部VarDecl的初始化。
当前仅支持函数body及可追溯普通块/if嵌套中的单变量声明、automatic非TLS plain int、单一直接
零参int prvalue调用和精确getter定义；不会剥离cast/comma或把函数指针调用
当成getter。重新执行getter输出检查，继承其全部外部协议与前提，再显式
要求本次调用执行选中定义、初始化正常完成。只建立初始化时的值关系。
词法祖先路径逐项唯一绑定并记录，循环/异常等其他祖先保持unknown；不证明
分支可达，不把conditional执行解释为所有调用都会初始化该变量。

模板实例可共享最终callee DeclRefExpr ID：选点使用唯一CallExpr的实际child
路径，不按该leaf ID索引。所有同ID叶出现必须childless且kind/type/category/
referencedDecl完全一致；callee decay、调用、变量、声明语句、owner和getter
仍要求唯一。该局部规则不改变其他checker的identity policy。
输出记录policy和共享出现次数；后续历史、数值域、纯度、动态链接、source/
deploy仍未证明。两次getter调用的结果不被当作同一个值。

`field_snapshot.check_query_initializer_to_statement`从fresh初始化关系构造内部
seed，复用`integer_selection._preserve_to_statement`的私有first-entry模式。
仅用于initialized local，不能与const快捷模式混用；公共调用者不能提交
成功seed。起点声明和目标必须为同块有序直接语句。

新模式仅排除target及之后同块兄弟子树中的protected reference分类；它
仍遍历全函数拒绝goto/label/lambda/asm/异常等，仍核引用唯一性。target前
地址/引用逃逸、array_filler引用及所有中间语句效果继续审计。
默认历史入口不启用该模式；新policy绑定报告hash，明确列出排除的引用ID。
结论严格止于该对象生命周期内目标首次入口、尚未求值任何target子表达式；
target自身计算、之后的写入、数值域、可达性/部署均未验证。

## 一元 native 调用的条件效果组合

`loop_exit_guards.check_iteration_bounds`显式接收相同一元/using选项，向其
fresh work检查传递；只有work通过后才消费外部声明区间并计算次数边界。
成功hash继承work策略与输入绑定，另外绑定声明区间，完整保留子调用前提。
次数边界不是完整迭代域：nested/work-body算术、输出覆盖、初始化/launch
域与FP值仍未建立。完整int32区间仅表示外部ABI范围，不表示变量实际遍历
该范围，也不是对未初始化值或越界访问的许可。

`loop_exit_guards.check_work_preservation`也可显式接收一元/using选项。
只在精确call回调中启用；其余work、guard、prefix及启用的nested结构仍逐项
检查。父报告继承实际消费的子调用前提，输入hash绑定builtin call策略；
一个call checked不能隐藏另一个无协议call或受保护存储写入。未使用协议
继续导致unknown。默认高层domain/initializer入口不自动开启新模式。

`builtin_calls.check_call_no_memory_write(..., allow_unary_float=True,
allow_using_shadows=True)`可显式选择一元wrapper路径：fresh检查完整外层调用
结构与实参，再fresh检查精确native leaf及现有
`builtin-leaf-effect-assumption/v1`。leaf假设必须覆盖该外层调用可达的全部
参数值，不能只针对一个采样值。无协议、错绑定、非布尔前提、实参或wrapper
写入均保持unknown；零参旧路径保留，默认不开启一元支持。

`checked`仅表示在声明前提下组成`exact_call_expression`的条件无写入，
external_leaf_effect_verified仍false。实参初始化/存活/边界与正常求值
前提向上传递；结构子报告继续保留callee/whole-call效果未建立标记。
父报告不把这些子标记改写成无条件证明。输入哈希绑定call策略及效果协议。

`column_loops.recover_with_call_effects`显式接收相同选项并重新消费每条精确
协议；循环体其它写入仍检查，保留未使用协议和unknown循环。恢复结果属于
外部效果前提下的路径，不能交给默认组合器冒充默认源码保持性证明。
开发驱动`--assume-unary-effects`仅用于敏感性实验，报告保存所有未验证前提；
不是设备库效果认证，也不授权GPU部署。

## native 外层调用与实参求值

`scalar_call_effects.inspect_native_call(payload, call_expression_id, leaf_call_id)`
从同一AST精确绑定直接float调用及其实参，独立检查实参求值，再fresh检查
wrapper到所选native leaf的参数链。不消费生成器报告或旧成功子结论。
支持范围沿用受限标量表达式检查器；递增、赋值、未知调用、间接callee等
保持unknown。局部数组与指针下标不是同一支持类别。

成功只连接调用身份、实参无显式内存写入与参数结构；无leaf效果假设，
`callee_effects_checked`及`whole_call_no_memory_write_checked`始终false。
实参初始化、存活、索引有效性与正常求值仍是前提。若实参通过而native链
失败，整体unknown，但保留实参子结论。成功哈希绑定native envelope、精确
outer call/argument ID与身份策略；不签发浮点值、循环或部署保证。

## native 参数转发结构

`scalar_forwarding.inspect_builtin_structure`只接受同一native envelope与
精确start declaration/leaf call ID，不消费预先签发的子结论。先检查
native builtin身份及形参读取，再检查wrapper每一级形参转发；终端call与
当前wrapper形参必须精确对应。成功报告绑定root、native envelope、所选
调用、声明及两层检查策略哈希。

该入口不需要效果假设，因而也不签发无写入结论。报告明确排除外层实参、
运行时定义/输入历史、浮点值和正常返回语义；读取其它函数的同类型形参
不能仅因leaf结构独立通过就拼接为成功转发。后续效果组合必须重新检查
外层实参并消费精确外部前提。

## builtin程序可访问存储协议

`builtin-accessible-storage-assumption/v1`与no_memory_write协议不同：允许
intrinsic具有inaccessible-memory效果和convergence约束，不声称完全无副作用。
协议绑定同次native envelope哈希、外层call ID、精确leaf call/decl ID，要求
`leaf_preserves_accessible_storage_assumed: true`及
`valid_execution_and_normal_return_assumed: true`，并保留非空evidence_reference。
这些是显式外部前提，probe IR不自动验证完整生产调用的参与、有效性或lowering。

`accessible_call_effects.check_callee`从完整AST fresh检查受限单return的
标量wrapper链、全部内层实参效果及native builtin身份。不检查外层实参；
其结论subject明确为callee_execution_only，outer_argument_effects_checked=false。
数组检查器消费该报告后仍遍历全部外层实参、默认实参、写入与对象效果，
所有义务通过且输入协议精确消费后才能条件建立保护对象存储保持。
protocol错绑、未知实参、额外未使用协议均不接受。无整核或部署保证。

## 单标量外部调用效果协议

`scalar-leaf-effect-assumption/v1` 绑定完整TU的`root_sha256`、外层完整
`call_expression_id`和外部无body的`leaf_declaration_id`。必须显式提供
`leaf_no_memory_write_assumed: true`、`valid_call_and_normal_return_assumed: true`
和非空`evidence_reference`；整数1不代替布尔true。

无写假设覆盖这个调用可达的所有float实参值，只描述外部leaf实现，**不覆盖
实参求值**。`scalar_call_effects.check_no_memory_write`重新检查直接callee、
完整受限参数转发链和实参求值效果，然后给出conditional的exact_call_expression
结论。已有子报告不能替代fresh检查；错绑、未知或预算不足保持unknown。
证据reference只记录为unverified，不认证SDK函数性质、运行定义绑定、数值值、
FP环境、纯度或机器码。实参初始化/存活/边界等子检查前提仍明确保留。
当前入口不改变默认循环恢复和部署门控。

## builtin 无写入条件协议

`builtin_calls.inspect_structure`与`check_no_memory_write`新增显式
`allow_unary_float=True`：仅支持native绑定的`__builtin_expf`/`__builtin_logf`
和普通按值float形参的直接LValueToRValue读取。未开启时保持旧子集。
`allow_using_shadows=True`可另启用受限引用展开身份规则；两项模式及策略版本
绑定structure_policy哈希，不修改AST。声明类型、引用类型、native实参ID必须
一致；引用/volatile/写入/调用/窄化实参均不支持。

一元模式的结构checked不认证builtin实现效果、返回值或FP环境。组合无写入
仍需要下述精确外部协议，并保留形参已初始化、存活且可读的前提；不能根据
ConstAttr或函数名字自动签发效果协议。wrapper链入口和循环恢复并未自动
启用此模式；leaf通过不等于外层exp wrapper及kernel调用已检查。

`builtin-leaf-effect-assumption/v1` 不提供返回值或浮点等价保证，只向独立结构
检查后的精确 callee 提供外部“实现不写内存”与有效/正常返回前提。结构检查
必须重新执行；零参或仅空字符串 literal decay 的参数求值另行确认，不能让
callee 前提覆盖 `counter++` 等外围求值。外部 evidence_reference 仅记录为
unverified，不由本协议自动核验。示例（占位哈希/ID 不能通过实际检查）：

```json
{
  "schema_version": "builtin-leaf-effect-assumption/v1",
  "native_envelope_sha256": "<full-envelope-sha256>",
  "call_expression_id": "<same-context-call-id>",
  "callee_declaration_id": "<same-context-callee-id>",
  "builtin_no_memory_write_assumed": true,
  "valid_call_and_normal_return_assumed": true,
  "evidence_reference": "<externally supplied justification, not verified by this checker>"
}
```

仅当实参/函数引用求值不写内存、精确 builtin 实现也不写内存，并且源调用有效
且正常返回时，组合所选 CallExpr 的 no_memory_write。结论为 conditional，
不是纯度、完整无副作用、外层函数/循环保持性或设备部署保证。没有此协议、
哈希/身份不一致或结构 unknown 时不得给出该条件结论。

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

构造实参恢复额外支持精确 alias→record ID 锚定且 record 内选定 ctorType 唯一
的直接构造；`constructor_identity.mode` 必须区分它与 AST 原有 conversionFunc
引用。此身份关联本身不建立复制/移动语义、命名对象值保持或动态调用值域。
对于无子节点的默认实参，额外的声明局部字面量恢复可记录精确参数 ID、位置、
构造声明和默认表达式，保留调用点原始 AST，不补造 child。字段 checker 独立
核对这些绑定、参数初始化式、类型与转换链，再检查整数值保持；同 TU 来源、
声明唯一性及无重声明仍属于前端可信前提，不宣称 checker 重验完整 TU。
支持边界见
`compiler/analysis/README.md`。

## 动态整数最小值的条件检查

`verification.integer_selection.check` 从完整 TU 的唯一表达式 ID 出发，核对
直接调用的精确函数声明与两个 const 整数引用参数。仅支持单 return、内建 `<`
和选择对应两个参数的三元表达式；不按函数名赋予 min 语义。比较两侧可以交换，
返回分支必须同步对应。调用必须在当前值表达式中立即读取，外围 IntegralCast
须对整个结果区间值保持。引用逃逸、函数体写入和任意实参计算不在支持子集。

输入 `declaration_intervals` 按精确变量/形参声明 ID 提供闭区间，`integer_types`
显式提供 ABI。两个操作数区间的最小值区间为端点分别取 min；它是给定域下的
值范围，不证明调用前的变量赋值、真实输入域或这些端点实际可达。
AST 忠实性、源有效性及引用对象/字面量临时对象的生命周期是显式前提。
不证明外围 ExprWithCleanups、对象复制、调用到 launch 的值保持或 GPU 行为。
默认节点预算 100 万、显式上限 1000 万，超预算 unknown；结果不能授权部署。

`source-constructor-values-check/v1` 将上述检查与同一完整 TU 中 fresh 恢复的
直接构造身份、literal/default 和完整字段映射连接。动态域按原始实参表达式 ID
提供，不接受预先给出的 checked；所有字段义务均满足才给组合结论，原始恢复
状态及 AST 不修改。检查构造求值时的字段域，不证明命名对象到 launch 的值
保持，也不解释字段名为坐标轴。复制和未知实参不因局部成功而获准；详见
`compiler/verification/README.md` 的源构造组合接口。

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

独立 `conditional-column-body-check/v1` 入口从完整 AST 的精确函数/循环 ID
重新观察坐标 header，并对整个受支持 body 检查受保护声明保持性。属性调用
必须逐项 fresh 组合 receiver/getter 的无写证据；协议须精确覆盖 body 属性。
`column-body-assumptions/v1` 显式绑定 root、函数与循环，要求源码有效和存储
不与受保护声明别名，引用不自动成为证明。默认源码恢复及列域门控不因此升级。
checked 不是整个 body 无写，也不建立 getter 值稳定、整数递推或列覆盖；
具体接口和支持限制见 `compiler/verification/README.md`。

`coordinate-column-header-observation/v1` 的 observed 仅表示受限直接属性起点和
unsigned compound increment 的结构及 getter/receiver 绑定已观察到；不表示
这些 getter 具有 CUDA/HIP 坐标语义。它不填写数值步长，也不建立 header
递推，父循环继续 unknown。body 保持标志由原受限副作用检查独立建立，依赖
源有效性和无别名前提；不证明正常完成、贡献或参与。必须另行检查 launch、ABI、整数转换/加法和循环体
保持性，不能将该观察替代下述列域门槛。原始初始化和增量 AST 保留在父报告中。

循环报告将`header_recurrence_observed`与`body_preserves_induction`、
`body_preserves_bound`分开。后两项只有在受支持的副作用子集中完成检查才为
`established_in_supported_effect_subset`；仅观察循环头不允许进入列域checker。
允许的存储目标为直接非保护变量及受限内建数组下标链；引用转换、逗号等复杂写入
目标和未支持节点（包括汇编）返回unknown。数组写入仍依赖不与受保护标量
别名的显式前提；这不是任意C++别名分析，也不证明循环体内存访问有效。
多层下标链最多 8 层，要求完整操作数、lvalue/类型证据和精确非引用根声明；
不能仅因数组存储根不在 protected 集合就跳过索引求值。每层索引仍参与完整
副作用检查，修改 protected 声明或包含不支持调用使整个 body unknown。
普通三操作数条件表达式仅扩大可遍历的 body 结构：条件与两个分支都须通过
副作用检查，常量条件也不跳过分支。它不建立条件值或终止性；条件左值作为
写入目标仍 unknown。此行为与常量求值器的 selected-branch 求值有意不同。

普通 signed-int 恢复可组合一层内嵌 for。内层须独立恢复，在非负 literal
起点 s、const 上界 b、正步长 d 下，计算 k=max(0,ceil((b-s)/d))，检查
s+k*d 可由显式 signed ABI 表示（包含末次增量）。随后分别对其 init、
condition、increment 和 body 检查外层受保护声明，不能用内层保持性替代
外层保持性。nested_loops 保存该条件证据，不输出 checked/deployable。
平面清单保留词法深度；仅函数顶层循环允许此组合，后代不能重置嵌套预算。
有限递推不证明内存有效、可达性、正常 body 执行或整核终止。默认副作用
检查器仍拒绝嵌套循环；只有上述 fresh 组合路径使用内部回调建立外层保持性。

body 的 bool SubstNonTypeTemplateParmExpr 只在替换为明确 typed bool literal
时作为无写表达式处理，参数 metadata 不得藏其它子表达式。可信前端的替换
关系仍属于假设，不独立检查模板实例化。if 两分支仍全遍历，不做死支删除。
无表达式 LoopHintAttr 包装只暴露其单个原始 ForStmt，不能重置词法深度或
绕过 body 检查。只针对变换前源码关系，具体 hint option/编译后效果不推断。

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

## 直接 record 复制的局部关系

`record-copy-check/v1` 从完整 TU 重新关联实际复制构造声明，检查空 body 和
全部直接内建整数字段的同字段读取。只有全部映射成立才输出 checked；字段交换
拒绝，副作用、复杂对象类型或绑定证据缺失保持 unknown。报告绑定 root、表达式
和外部整数 ABI；节点预算不包含解析与哈希的总资源限制。

该关系仅覆盖实际复制实参在本次构造求值中的字段值，不生成数值域。
源存活、字段已初始化且读取有定义、程序有效和正常返回是显式前提。
`source_declaration_id` 只表示词法绑定：lambda 捕获解析、运行时源对象身份、
初始化至复制之间的值保持，以及实际 launch 均未建立。不能把另一次构造的
字段域直接搬入本报告；`source_program_checked` 与 `deployable` 始终为 false。

`capture-source-check/v1` 可在独立的四项生命周期/闭包来源/同动态调用/源有效性
外部前提下，检查普通自动对象的全引用捕获链。必须重新从 AST 恢复目标 body
路径并核对每层原生正面映射；不通过元数据缺失推导任何否定事实。
条件身份结论不覆盖对象内容、调用是否发生或 launch；evidence_reference 只记录，
不当作已核实证据。原生元数据属于可信前端，既有部署门控仍保持 false。

## 初始化历史中的数组调用请求

`initializer_domain.check_to_statement` 的 `call_protocols` 可包含
`array-call-preservation-request/v1`。这是重新检查的请求，不是成功证明；
仅允许以下五个字段：`schema_version`、`native_envelope_sha256`、
`call_expression_id`、`protected_declaration_id`、`accessible_call_protocols`。
哈希绑定当前完整 native payload，两个 ID 分别绑定实际调用和历史链保护变量；
内层 accessible 协议映射最多 64 项，交由数组 checker 重新绑定、检查。

历史检查器启用数组 checker 的 scalar-operator、literal-default 和 native
对象检查，要求 fresh 结果同时满足 `status=checked` 和
`protected_storage_preserved=true`。成功子检查的假设并入父报告；失败调用 ID
保留用于诊断。旧成功报告、错绑请求和未消费请求不能解除义务。

该结果仅覆盖初始化之后到目标语句首次正常进入前的值保持，不覆盖目标语句体、
后续迭代、可达性、线程坐标含义或 GPU 执行。数组范围、对象存活、有效执行、
外部 leaf 效果等条件不会因组合而被证明；source/deploy 标记仍为 false。

### 受限字面量数组初始化效果

循环体效果检查仅支持一维 `float[N]`（1 ≤ N ≤ 4096）的字面量/隐式值
初始化。必须检查 Clang 的全部语义初始化槽位：完整初始化的 `inner`，或
部分初始化的 `array_filler`（首项为隐式值初始化，其后为显式元素）。
两种布局混用、非浮点槽位、复杂表达式、调用、写入、引用/record 构造保持
unknown。这里检查的是效果，不推导数组值、不支持一般聚合初始化；不能
因普通 AST 遍历没有看到 `array_filler` 内容就将其视为无副作用。

### 初始化域到嵌套循环入口

`initializer_domain.check_nested_entry` 重新运行初始化到外层首次入口的历史
检查，再将同一个源声明加入外层受保护集合。私有 work worker 检查原始外层
init/condition/increment、prefix/guard 和全部 work；内层前后兄弟语句不能
绕过保护，嵌套 header/prefix/guard/work 继承该保护。公开的原有 work API
不接收成功报告或额外的“已证明域”，其默认行为保持不变。

组合要求相同 root 哈希、整数 ABI、精确 inner ID 和唯一的 checked 嵌套路径，
历史和工作调用协议分别重新检查，未消费协议保持拒绝。
`initializer-to-nested-entry/v1` 的 `value_preserved_to_nested_entry=true`
仅表示：在显式前提下，每次实际到达该内层循环入口时保留初始化域。
它不证明实际到达、执行次数、终止、整数溢出或完整迭代域；所有外部 leaf、
有效执行、存活、无别名和无异步干扰条件仍须成立，source/deploy 保持 false。

### 使用初始化入口域的次数边界

`check_nested_iteration_bounds` fresh 执行上述嵌套入口检查，再把该精确源
声明的区间注入 `check_iteration_bounds`。调用者只能提供其余入口区间，
不能覆盖源声明域；缺失、额外或未消费域由独立边界 checker 拒绝。历史、
外层工作、内层工作协议分别重新检查，root 哈希必须一致。

`initializer-to-nested-iteration-bounds/v1` 同时保留 `entry_check` 和
`iteration_check`；`source_interval_origin` 标记 fresh 入口链，
`remaining_external_declaration_intervals` 明列仍需外部保证的域。子边界
报告本身仍是条件命题，不因父级组合就被改写成“全部输入事实已证明”。
`work_count_bounds` 仅针对每次实际到达的单次内层循环执行，不累计所有
外层迭代；外部区间也须在该次内层入口成立。不宣称精确逐输入次数、完整
覆盖、可达性、终止、浮点等价或部署安全，full-domain/source/deploy 仍 false。
