# 关系恢复

## 局部贡献的声明求值边界

`local_contribution.recover`的逐列平方和子集要求accumulator和每次迭代加载的
const float都是普通自动存储期变量。static、extern、TLS及未支持声明属性返回
unknown，不能仅看到初始化表达式就认为它每次执行。成功报告中的
declaration_evaluation只描述受支持声明被求值时的初始化规则，不证明前缀可达、
输入值、别名、浮点模式或两份源码之间的局部值对应。

循环后、consumer前只允许无初始化、无求值子节点的固定正float[N]局部数组，
或extern float[N]/float[]声明；可有单个无子节点CUDASharedAttr。固定/动态HIP
共享数组形状均保留，不把语法storageClass缺省称为共享对象的自动生命周期。
普通extern数组声明不引入局部初始化；其外部分配、容量与可见性仍由其他门槛
负责。VLA即使没有CallExpr也可能在维度表达式中修改
accumulator；因此同时检查精确数组类型子集和声明children，不只匹配字符`[`。
未知属性、static/TLS数组及其它声明保持unknown，不实现通用别名或VLA分析。

真实Clang/CPU回归包含持续累加、静态加载冻结首值和数组维度写入；source.run
到normalization_output的无mock负例确保局部失败不被下游成功状态覆盖。这些是
源码分析回归，不是生产语料、HIP设备问题复现或GPU正确性结果。

## 协作宽度的显式引用用途

`width_uses.inspect(root, kernel_id, int_bits)`从完整TU fresh恢复归约链及block/XOR，
以两者共同width声明ID选点，不按变量名或字面量值选择。遍历整个TU的该声明
DeclRefExpr，按精确AST位置分类：XOR初始偏移、intrinsic宽度、group除数、lane
余数和partial组数除数。重复/冲突身份、类型证据缺失和未展开别名保持unknown。
不支持的引用（包括取址、额外算法用途、未调用函数和printf诊断）保留完整祖先
与所属函数并使总体unknown，不提供“诊断无害”的例外。

即使五类显式用途均分类，结果也只是evidence，checked/source_program_checked/
deployable均false。它不覆盖AST中被折叠或省略的语义引用，不验证转换、全部
副作用或源目标等价；不能作为单独的改写许可。默认100万节点，最多1000万，
预算不包含fresh子恢复器的全部时间/内存开销。

## 同 TU launch 身份归一化

launch_facts 在解释目标前按非空 Clang ID 收集 CUDAKernelCallExpr，仅完整节点
一致的同 ID 出现可合并；site.ast_occurrences 保留出现次数。不同 ID 不合并，
缺 ID 保留各次出现。同 ID 内容冲突（包括指向不同 kernel）使整份报告 unknown、
sites 为空，不能由目标过滤绕过冲突。函数定义的唯一性检查不因此放宽。
这是单 AST root 内的语法身份归一化，不是 host 控制流、调用次数或可达性证明；
一个 lambda 节点可能运行零次或多次。other_kernel_sites 仍计原始出现次数。

## 直接坐标循环头：结构观察而非递推证明

列循环报告新增完整 `initializer_ast`、`increment_ast`，后者保留 CompoundAssign
的 computeLHSType/computeResultType。`coordinate_header_observation` 仅观察
`int <- IntegralCast(unsigned PseudoObject)` 起点、同 induction 的 `< signed参数`
条件和 unsigned PseudoObject 的 `+=` 步长；复用 initializer_value 精确绑定静态
无参 getter 与 receiver，不按 threadIdx/blockDim 名字赋予语义。

即使子报告 `observed`，循环和总恢复仍 `unknown`，数值 step 为空，
header_recurrence_observed 为 false。body 保持性通过原受限副作用检查单独建立：
保护 induction、边界及两个 receiver 声明；失败保存 body_effect_reason。
body_effect_unknown_range 保存首拒绝范围；source_validity 前提显式标为未证明。
循环体改 induction 也可能具有相同 header 观察，但 body 保持性不得建立。
即使 body 检查成功，也以有效源程序和 memory_no_alias 为前提，不证明 body 正常
完成、分支一致、数据贡献、receiver purity 或参与，绝不能据此放行。
未知 getter、额外 cast/算术及不支持
的 computation type 不获得该观察。旧 signed 常量递推路径保持不变。

坐标语义、实际 launch/block 宽度、显式 ABI、起点转换、unsigned 加法及赋回 int
（包括末次增量）尚待独立检查。当前 thread_start/column_domain 等消费者继续
拒绝这些 unknown 循环。symbol-filtered AST 缺 getter 声明时不拼接别次 AST 补全。

## 列循环副作用边界（2026-09-21修复）

声明类型分类同时用于引用初始化和存储目标：优先使用声明上的desugaredQualType，
不能以DeclRefExpr的值类型代替变量声明类型；未展开别名或未知非builtin类型保持
unknown。该分类不改变循环头的既有类型匹配。induction仅支持自动存储期，
static/thread_local等拒绝，不按每次进入循环都重新初始化来建模。

循环体采用受限节点白名单与存储目标分类，不能识别的写入目标不得被当成纯读。
`output[col]`将col作为索引读取；直接写col/边界/起点、引用逃逸、复杂左值写入、
不透明汇编或其它未支持效果使恢复unknown。报告分开记录观察到的循环头和
循环体是否保持induction/bound；保持结论仍带memory_no_alias和有效源程序前提。
真实Clang回归覆盖引用转换、逗号左值和汇编，不算独立ML代码谱系。

row-prefix报告的source_offset/output_offset保留完整`offset_ast`及`update_ast`，
包括乘法外层转换；结构恢复不解除整数转换或指针有效性义务。两侧同样窄化仍
可以是匹配的结构，必须交由独立整数checker检查，不能将cast signature相同当证明。

块归约报告另保留 `shared_access_asts`：writer/gather的完整谓词及整数下标表达式，
包含尚未检查的转换。保留AST不等于建立访问语义，需显式坐标和ABI下的独立检查；
仅凭剥离转换后的lane/group声明引用，不能解除下标或条件的值保持义务。

## 归约调用的入口控制义务

`entry_control.recover(root, function_id, callee_id, call_range)`以同AST精确callee和
唯一call range定位顶层直接调用或单变量初始化调用，扫描入口至首次调用的前缀
及目标实参。仅接受受限表达式和直接For；条件调用、提前返回、跳转、嵌套循环、
短路、汇编或未知节点保持unknown。前缀最多10000节点、深度64。

`entry-control-obligations/v1`保存前缀调用的精确目标及normal_return未建立义务、
循环range及termination未建立义务。MemberExpr仅记录声明ID，不证明dispatch或
receiver行为。`reduction_chain.entry_control`自动保存该子报告；顶层结构recovered
不会被误标为参与证明。它只描述首次目标调用前缀，不分析后缀回跳或多次调用的
同步序列，不证明内存/算术有效性、循环终止或外部调用正常返回。
即使recovered，participation仍为not_established，checked/deployable均false。

计划联合恢复数据索引、线程分工、collective 和输出归属。存在多种解释时保留冲突，并给出未知或拒绝原因。

当前实现：`src/wavebridge/analysis/source_facts.py` 从已采集的 Clang AST
提取直接调用、声明引用、运算符和循环的结构事实及原始源码范围。
这不是跨 lane 关系恢复器。人工关系 oracle 不计入自动恢复覆盖率。

```bash
PYTHONPATH=src python3 -m wavebridge.analysis.source_facts \
  artifacts/input-ast.json --output artifacts/new-source-facts.json
```

只接受 `clang-ast-source/v1` 的 `collected` 工件，输出文件不可覆盖。
调用目标只从 callee 表达式识别，不能在参数中搜索函数名补填；间接和
不支持的调用保留未知。标识符以输入工件规范化哈希和 root index 隔离，
Clang 内部地址不能用于跨次编译连接。规范化哈希不等于输入文件字节哈希。

实际 HIP 输入已提取 `__shfl_xor`、barrier 和 helper 调用，但当前 SDK 把
`threadIdx.x` / `blockIdx.x` 表达成属性 getter 调用，尚不能解释其语义。
过滤后的 AST 也可能只有常量引用而没有初始化定义。两者都不能靠名称猜测。
后续需建立声明/调用闭包、控制与存储依赖、launch 对应，再检查跨 lane 关系。

`analysis/declaration_index.py` 进一步按同一 AST root 内的精确 ID 连接声明引用，
并记录声明是否带 initializer/body；引用 stub 不作为完整声明。
`previousDecl` 仅记录而不追链，未解析引用保留，索引成功不是闭包完整或语义正确。

```bash
PYTHONPATH=src python3 -m wavebridge.analysis.declaration_index \
  artifacts/full-tu.json --output artifacts/new-declaration-index.json
```

## 受限整数常量

`integer_constants.evaluate(root, declaration_id, int_bits=...)` 以一个 AST root
和精确声明 ID 为输入。整数宽度是外部显式条件，不从名字猜测，也不借用 qdot
检查器的无界整数语义。仅在支持的 signed-int constexpr 表达式内求值；
不支持的类型/转换、溢出、除零、循环引用和缺失定义必须返回未知。

常量值不带自动角色分类：求出 32 不代表它是协作宽度，更不能据此修改数据格式。
后续还必须将该声明在索引、collective 参数和 launch 中的使用关系分别恢复。

## getter 返回调用链

`return_trace.trace(root, declaration_id, max_depth=16)` 针对单个 root 内的
单 return、无参数 wrapper 追踪精确声明引用，记录每层 body/range、转换及
外部调用的实参 AST。到达仅有声明的外部函数只是调用链端点，不自动赋予
该函数线程索引或 collective 语义。完整声明链与外部语义协议需要分别建立。

返回算术、多个语句、循环链、缺失目标或需要参数替换的内部调用保持未知。
跟随 MemberExpr 只建立调用证据，不证明 receiver 无副作用，也不证明删除
记录的窄化转换是合法的。结果不能作为代码改写或部署许可。

v1 的 step 证据另保存完整 return/callee AST、调用结果类型、声明 kind/signature/
storageClass，以及中间 MemberExpr 的全部 child（不视为已验证的纯 receiver）。
同一 exact Clang ID 出现多个函数节点时返回 `callee_declaration_ambiguous`，
不按遍历顺序覆盖。此门控不解析不同 ID 的 C++ 重声明/定义链，也不证明语义实体唯一。

## 从源码到列递推证据

```bash
PYTHONPATH=src python3 -m wavebridge.source \
  benchmarks/cases/llama-rmsnorm/baseline/rmsnorm_logical32.hip.cpp \
  --compiler /path/to/hipcc --compiler-arg=--cuda-device-only \
  --symbol rms_norm_f32_logical32 --int-bits 32 --output-dir artifacts/new-columns
```

入口直接采集完整 AST，再按唯一入口声明提取受限 `for` 列递推；不读人工
Kernel JSON 或 oracle。输出目录必须不存在，其中 `ast.json` 与 `report.json`
以哈希绑定。多个编译视图或同名入口不猜选；报告 `analyzed` 仅表示分析执行，
具体循环仍可能为未知。位宽是外部声明，不代表已自动建立目标 ABI。

`column_loops.recover(root, function_id, int_bits)` 支持 signed-int 的
`i=start; i<bound; i+=positive_constant`，以声明 ID 匹配条件与增量。
起点保留源码表达式引用，不预设为线程 ID；额外循环变量/边界写入、可疑引用
别名、调用或复杂控制流保守拒绝。普通 `output[i]` 下标读取不是对 `i` 的写入。
递推仍以无溢出、合法域、未建立的别名前提为条件；没有证明输入覆盖、launch
一致性、归约通信或浮点等价，不生成可部署候选。

源码入口还为循环起点声明记录 `start_initializer_evidence`：保留完整初始化
表达式、其中的调用及getter返回链。特别是 HIP `PseudoObjectExpr` 不会被
简化为“最后一个child就是值”。找到OCKL调用不等于证明起点值是线程索引；
报告保留 `value_equivalence=not_established`、`start_semantics=unknown`。
原始AST哈希和此次分析实现文件哈希同时记录；不支持的调用种类亦保留未知，
不从调用计数中静默删除。

`value_link` 子报告（`initializer-value-link/v1`）进一步连接受限初始化式与
产生结果的调用。支持无参直接free call，以及HIP式静态MS属性getter：恰好一个
语法属性、一个plain-lvalue OpaqueValueExpr receiver和一个无参CallExpr。
依据Clang PseudoObjectExpr的结果类型/value-kind不变量，在**全部语义child**中
要求唯一匹配结果；不按函数/属性名称识别，也不直接选择最后child。属性、语义
receiver和成员callee的receiver须完整一致，成员目标须exact ID唯一、static且无形参。
可变参数getter不支持；调用必须为prvalue，Paren类型/值类别必须与子表达式一致。
外层仅接受Paren/IntegralCast；转换按外到内记录，不删除窄化或宣称值保持。
非静态getter、额外算术、缺类型、结果歧义、不同receiver或未知cast保持unknown。

该不变量的实现依据是已检视LLVM提交
`0b9310c6e4416ee48c07edfef81144e22850dfe7`中
`clang/lib/AST/Expr.cpp`的`PseudoObjectExpr::Create`与
`clang/include/clang/AST/Expr.h`的语义child说明；**不是对实际HIP编译器内部实现的验证**。
报告显式保留“生产者满足该不变量”的外部前提，源码入口绑定实际编译器/AST/实现哈希。
`recovered`只说明条件结构连接，初始化值等价、坐标语义、整核正确性及部署仍未建立。
`receiver_purity=not_established`也保持不变，不能据此删除receiver求值。

## 块级索引初始化证据

块级归约恢复还保留`index_initializers.group/lane`的完整初始化AST，不仅保留
`coordinate_asts`中的左操作数。这样独立检查可见除法/取模、宽度操作数转换和
最终赋给const int的窄化，而不从扁平cast列表猜表达式顺序。恢复报告自身的
coordinate/conversion语义状态不因此升级；组合检查见verification说明。

## XOR 归约 helper

`xor_reduction.recover(root, function_id, shuffle_declaration_id, int_bits)`
恢复有限的单参数float helper：`offset=width/2; offset>0; offset>>=1`，
循环体为同一accumulator加上选定函数的三参数调用，最后返回该accumulator。
width来自真实常量定义；额外语句、错误ID、改变条件/更新均未知。
`shuffle_declaration_id` 是显式外部选择，未证明其intrinsic语义。

可保存绑定原始AST哈希的恢复结果及独立条件路由检查：

```bash
PYTHONPATH=src python3 -m wavebridge.analysis.xor_reduction AST_REPORT.json \
  --root-index 0 --function-id CLANG_FUNCTION_ID --shuffle-id CLANG_CALLEE_ID \
  --int-bits 32 --output artifacts/new-xor-report.json
```

Clang ID仅对指定AST工件/root有效。`source_program_checked=false` 始终保留；
路由检查的条件保证见 [协议范围](../../docs/contracts.md)，不能当成完整kernel验证。

## 块级共享 partial 阶段

`block_reduction.recover(root, function_id, reduce_id, barrier_id, int_bits)`
提取有限七语句模式：首次归约、group/lane划分、lane0写partial、barrier、
按lane读取partial并补零、再次归约返回。width/BLOCK从实际声明求值，所有
参数/索引/调用按声明ID关联；缺失阶段、错误索引或谓词保持未知。

外部选择reduce/barrier ID不赋予它们语义。group和lane的坐标AST分别保留，
不能因表达式名字相似认定其值相等；坐标与整数转换范围是独立未证明前提。
独立 `verification.block_routes.check` 检查条件模型贡献计数，不为源码签发保证。

## 入口可达的归约候选发现

源码入口同时输出 `reduction_discovery`：从唯一入口沿直接调用的精确声明 ID
寻找可达 helper，再尝试上述受限结构恢复。不按函数名识别算子，不要求用户
填写 helper、shuffle 或 barrier ID，不把不可达的相似函数计入候选。

这只是调用与结构候选发现，不是 intrinsic 语义识别或完整调用图证明。间接、
特殊调用、缺少定义和预算耗尽必须保留诊断；发现部分候选不能掩盖未遍历部分。
候选中的外部语义、坐标、转换及收敛义务不自动解除，源码入口也不自动将其
提交给条件路由 checker 后签发“源码通过”。旧的显式 ID 接口仍可用于诊断。

精确 `MemberExpr` 调用仅在同 root 声明明确为 `static` 的 `CXXMethodDecl`
时加入调用边。receiver AST 保留且其语义未建立；virtual、缺失成员声明或
未证明 static 的调用仍为 unresolved。此规则可以接入 HIP 静态属性 getter，
但不证明属性结果等于线程坐标，也不删除 receiver 或整数转换。

Clang 的 `BuiltinFnToFnPtr` callee 转换可穿透到精确声明引用，和其它允许的
callee 转换一起保存在 `callee_casts`（类型、范围、未解除义务）。这只补全
声明关联；没有函数体的编译器 builtin 仍记缺定义，外部语义不因此建立。
任意指针 BitCast 等其它转换仍不支持。

## 局部列贡献到消费调用

`local_contribution.recover(root, function_id, int_bits)` 针对顶层相邻的零初值
float 累加器与列循环，恢复 `const float v=input[i]; acc += v*v`，并关联后续
直接消费 `acc` 的调用及实参位置。列下标、乘数和累加器均按声明 ID 核对。
消费前仅允许无初始化的数组声明；条件消费、额外更新或带副作用实参不支持。

报告保存源码范围、列递推、输入参数和消费声明 ID。它只描述该局部片段；
前置指针定位、完整输入别名、线程起点、consumer 的实际语义及浮点结果尚未
证明，不能把它与条件列覆盖检查直接合成为完整 kernel 保证。

## 归约结果到输出列

`normalization_output.recover(root, function_id, int_bits)` 在局部贡献恢复基础上，
检查严格后缀：归约调用结果赋给 total，`scale = external(total/count + epsilon)`，
随后列循环执行 `output[i] = scale * input[i]`。count 必须对应局部贡献循环的
边界参数，两循环按起点、边界和步长关系对应，写入与读取下标必须是输出循环
自身的 induction。错误下标、错步长、额外写入与隐藏控制流不在支持范围内。

external 的函数 ID 和转换证据会被保留，但不会根据名字认定它是 rsqrt。
整行基址、launch、alias、外部接口和浮点数值关系尚需另外建立；该后缀恢复
不签发可部署工件，也不声称完整 RMSNorm 正确性。

## 行偏移前缀与 launch 结构

`row_prefix.recover` 核对严格四语句前缀：row/start声明，以及输入、输出参数
分别加上同一 `cast(row)*count`。两侧声明引用、乘积类型及完整转换结构需要
对应；不根据 `long` 拼写认定位宽。初始化表达式与getter调用证据原样保留，
行/线程坐标含义、指针范围及转换安全性仍未建立。

`launch_facts.inspect(root, kernel_id)` 收集同AST root中精确引用目标kernel的
`CUDAKernelCallExpr`，保存配置调用的四个实参和kernel实参AST。它不求dim3
构造结果、不检查host可达性、不验证launch是否与kernel的分工一致；间接目标
与不支持配置形状保留unknown。源码入口将二者作为独立证据字段输出。

launch site 的 `parameter_bindings` 按精确 kernel 定义与实参位置关联形参ID，
保存实参AST，不猜数值；缺唯一函数定义或参数数量不匹配时绑定为unknown。
前两个配置实参另记录 `configuration_constructor_arguments`，保存显式构造
目标、参数位置、默认参数来源和转换链。`pre_conversion_constant` 仅是源码
叶表达式的转换前常量；它不是已证明的dim3字段值或实际grid/block大小。
不带默认表达式内容的AST节点不得被猜成1。

`constructor_fields.recover(root, constructor_id)` 核对唯一空body构造定义，
按FieldDecl与ParmVarDecl的精确ID恢复直传初始化及参数位置。允许字段交换，
但必须显式呈现交换后的映射；不会将第一个实参固定解释为x。字段与参数
desugared类型须对应，额外body写入、算术、base/delegating初始化或不支持转换
保持unknown。能定位直接所属record时核对全部字段；否则保留所有权不完整标记。
源码入口将其保存为构造参数报告的 `field_initialization`，仍不签发配置正确性。

## launch 前的整数守卫

`launch_guards.recover(root, launch_id, int_bits)` 从唯一 host 函数内的指定
launch 回溯顶层提前返回守卫。受限模式为 signed int 局部常量与整数字面量
的 `<`、`<=`、`>`、`>=` 比较，使用 `||` 组合拒绝条件，再对存活路径取
区间交集。报告绑定变量声明、守卫和 launch 的源码位置，不根据变量名认定
行数或列数。支持直接 launch 和单一 launch 的 `do { ... } while (0)` 包装。

源码入口将结果保存为 site 的 `host_guard_intervals`。它仅给出执行到该
launch 的必要条件，不证明 launch 一定可达、主机函数正确或配置字段值。
mutable/volatile、地址逃逸、不支持的控制流或转换保持unknown。源程序有效性
及 signed int 位宽仍是前提；这些区间不是外部合法输入/浮点数值协议，也不会
使 `configuration_check` 自动接受 symbolic 实参。

不符合该模式的普通 host 错误检查可以保留为 `skipped_guards`，但不能贡献
区间约束。跳转绕过、嵌套可调用对象等不支持结构则阻止恢复；普通调用的存在
不会被误判为边界成立的证据，受保护变量仍须通过只读使用审计。

## 显式全掩码四参数 XOR 结构

`xor_reduction.recover` 保留原三参数路径，新增四参数
`(mask, value, offset, width)` 的受限结构。按精确 callee/变量 ID 关联，不按函数
名字认定 intrinsic。只接受 `int_bits=32`、width 32、类型为 `unsigned int` 的
显式字面量 `4294967295`（可有括号）；保存 mask 原 AST、类型、值和源码位置。
动态/部分/带转换掩码及四参数 width64 返回 unknown，不降级为忽略 mask。

`recovered` 不证明 mask、XOR intrinsic、收敛或浮点语义。条件路由模型不建模
mask，结果中明确 `models_mask=false`；全32 lane在每次调用时活跃且收敛是外部
前提，不是恢复结论。CLI 对不支持的 mask 不调用路由 checker。
真实 CUDA 端口可自动发现该 XOR helper；后续 barrier callee 接入后也能发现
block helper 的七阶段结构。仍不能生成已验证候选或把同一案例的语言端口算作新谱系。

块级恢复只在无参 barrier 调用目标位置接收 `BuiltinFnToFnPtr`，按精确函数 ID
绑定，保留原 callee AST、source/destination type、cast kind 与 range。
参数位置、reduce callee 上的此转换以及 BitCast 不因此被接受。所有坐标、
转换、reduce/barrier 语义保持 not_established；选择一个声明不证明它真是 barrier。

## 累加器到归约 helper 的结构连接

`reduction_chain.recover(root, function_id, int_bits)` 从同一个AST重新运行局部贡献
与可达归约发现，不接收调用者填写的关系报告。它要求consumer对应唯一block
候选、累加器实参位置对应block的float形参、block的reduce目标对应唯一XOR
候选、两者width一致，且列步长等于block helper声明的线程数。预算未完成、
定义缺失、歧义及不一致均为unknown，不按函数名或候选顺序猜选。

源码报告新增 `reduction_chain`，保存三段精确声明链接与调用源码范围，继承
掩码和未解除参与前提，保留未解析调用。`recovered`只描述这条累加器结构链：
它不证明容量/别名、坐标相等、实际launch、收敛或浮点等价，也不包括完整输出
后缀；所有部署/检查标记仍为false。

`shared_storage` 子报告进一步按调用范围、callee ID及形参位置连接直接数组实参。
只接受括号与单次ArrayToPointerDecay，数组须在caller顶层、调用之前声明。
不支持指针别名、指针算术或任意cast；不能因为两个数组类型相同而互换声明。
该字段有独立status，unknown不会抹掉已有累加器链，也不能被忽略后视为存储已验证。

Clang的`float[N]`类型提供声明元素数，不推断字节数或实际可访问容量；
`CUDASharedAttr`才作为共享属性的源码证据。动态shared数组保留空extent并要求
launch字节数，普通无界extern数组要求外部分配依据，普通局部数组不宣称共享。
带extern的数组即使有书面extent，也不据此认定本地静态分配；shared仍要求
launch容量依据，普通extern仍要求外部分配依据。声明extent与分配来源独立记录。
即使声明元素数不足也只报告真实extent，不签发容量通过；容量检查、别名分析和
属性的目标语义仍是后续义务。完整原始实参AST、数组声明位置和类型均保留。

## 直接构造表达式的受限身份关联

`constructor_arguments.inspect(..., max_ast_nodes=None)` 保留原
`CXXFunctionalCastExpr.conversionFunc` 入口，额外接受一类直接 `CXXConstructExpr`：
表达式的 `typeAliasDeclId` 必须在同 TU 唯一关联到 alias 声明，再沿单层
ElaboratedType（可省略）到 RecordType 的精确 CXXRecordDecl ID。完整 record
中必须只有一个直接构造声明与表达式的 `ctorType` 完全一致；构造声明 ID
也须在完整 TU 中唯一。没有类型 ID 锚点时不按类名或全局签名猜测。

类型比较优先使用 desugaredQualType；仅该键不存在时使用 qualType，仍须与已
精确绑定的 RecordType 拼写一致。Clang 18 在展开前后打印拼写相同时省略该键，
见 [createQualType 实现](https://github.com/llvm/llvm-project/blob/llvmorg-18.1.8/clang/lib/AST/JSONNodeDumper.cpp#L287-L301)。
这不是“所有缺少解糖证据的 alias 都安全”：alias→record 的精确 ID 链仍必需，
不同拼写、缺 ID、显式空或 null 的展开值继续 unknown。

这依赖 Clang JSON AST 的明确不变量：`ctorType` 来自已选构造函数的
`getConstructor()->getType()`，见
[LLVM 17 JSONNodeDumper](https://github.com/llvm/llvm-project/blob/llvmorg-17.0.6/clang/lib/AST/JSONNodeDumper.cpp#L1283-L1285)。
有基类、模板成员或 using 选择路径的 record 暂不支持；非 complete 构造、
复杂 alias 链、重复 ID、多个同签名候选均 unknown。扫描预算默认每次 100 万，
可显式提高至最多 1000 万；不是总内存/时间限制，旧显式引用路径不增加扫描。

报告 `constructor_identity.mode` 区分原始 conversionFunc 引用与上述推导关联；
后者的 `constructor_reference` 是关联结果，不能称为 AST 原有 conversionFunc。
仅构造身份关联不证明字段值、复制/移动语义或变量到 launch 时保持不变。
实参中的未知调用与无法关联的默认实参来源继续阻断检查；不会把 std::min 的名字当作
语义契约，也不会把命名 dim3 对象的复制直接替换为其声明时字段值。

直接构造路径中的空 `CXXDefaultArgExpr` 可按实参位置关联到所选构造声明的
唯一参数及其本地 initializer；只支持内建整数 literal、括号和 NoOp/IntegralCast。
参数、默认子树 ID 必须可在完整 TU 中唯一定位；重声明链、继承/隐式构造、
调用、改写表达式及缺来源保持 unknown。不会把缺来源默认值一律填成 1。
原调用点保存在 `argument_ast`；`default_source_ast` 和
`default_source_binding` 单独记录来源，`default_constructor_declaration_ast`
保留选定声明供字段 checker 核对。已有带子节点的默认表达式继续走原路径。
来源恢复不等于整数转换安全；窄化仍由独立字段 checker 拒绝。
