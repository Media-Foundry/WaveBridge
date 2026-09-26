# 编译器关系检查

## 显式非负路由的条件舍入误差界

`verification.block_roundoff.compare(source_model, target_model,
leaf_upper_bound=Fraction(...))` fresh 调用已有 block_routes.compare，再逐加法
传播深度、绝对舍入余量和计算值上界。完整证明见根目录
[PROOF_PACKAGE.md](../../PROOF_PACKAGE.md)。所有计算采用精确 Fraction，报告
分子/分母为十进制字符串，不用浮点近似判断接受。

两侧叶值逐线程相同且在 [0,M]，计算值非负，局部加法误差不超过
`u*(a+b)+eta` 是显式外部前提（u=2^-24，eta=2^-150）。每步有限值域检查失败
返回 unknown；贡献缺失/重复沿用原 route 拒绝。不推断真实 accumulator 的 M，
不把模型与源码的对应、实际 GPU/FTZ/重排假设或 frozen atol/rtol 判为通过。

checked 仅表示条件模型上界：每侧 `abs(output-S) <= r*S+A`；两侧
`abs(source-target) <= (r_source+r_target)*S+A_source+A_target`。
报告的 difference_bound.relative_coefficient 是两个单侧系数之和；S 是共同
非负精确叶和。初始 shared 零和各加法余量保守计入，不要求舍入误差独立。
这不是 IEEE 逐位等价检查，numeric_contract_checked/deployable 始终 false；
局部平方和、除法、epsilon、rsqrt 与输出乘法的误差传播尚未连接。

新增 `block_roundoff.compare_sum_squares(source_model,target_model,ncols=...,
input_abs_bound=Fraction(...),source_accumulation="fma",target_accumulation="separate")`
在显式 `t+k*block<ncols` 和零初值模型中计算每线程迭代数，分别传播 FMA 或
分离平方/加法的局部误差与计算值域，再接每侧路由。最多64次局部迭代，预算
耗尽保持unknown；这不是实际源码或编译模式的自动识别。

它只要求共同原始行输入，不要求两侧已舍入的局部叶相同。报告保存每侧route
checks，不继承原比较接口的共同computed-leaf假设。局部上界由输入幅值和
列分配推导，不把未舍入的数学平方和上界当成浮点accumulator上界。
结果相对共同精确平方和Q给出误差，仍未涵盖除法、epsilon、rsqrt、最终乘法；
整核数值协议和部署字段仍为false。扩展证明在PROOF_PACKAGE.md末尾。

## 局部累加器与列循环的 typed AST 对应

`verification.local_structure.compare(source_root, source_kernel, target_root,
target_kernel, int_bits=32)`分别fresh恢复局部贡献，比较自动累加器声明和完整
ForStmt。它不是只比较sum_of_squares标签：保留节点种类、类型、转换、运算符、
操作数顺序、CompoundAssign计算类型以及显式fpoptions。仅去掉位置、原节点ID、
名字及使用标记；未知节点/字段、别名类型、重复声明身份及预算耗尽保持unknown。

声明按恢复角色对应，角色映射必须单射；参数位置和类型纳入模板，防止换成
另一个同类型参数后被重命名掩盖。其它引用只允许独立求值成功的整数声明常量，
保留类型、实际值及原求值报告，并逐项核验求值报告中递归依赖的声明唯一性。
原始角色ID、consumer位置和root绑定哈希仍保存。
模板按实际结构比较，不以哈希相同代替结构相同。

成功为evidence/local_structure_equal=true；不相同为结构rejected，而不是数值
不等价的反例。prefix不在模板内：在循环之前修改input指针仍可具有相同模板；
consumer也在所选片段之后。因此entry_value_correspondence、consumer_correspondence
及leaf_value_correspondence均保留not_established。源有效性、指针内容/别名、
整数域与FP编译/执行环境需要另外建立，不能通过“相同结构”默认补齐。
节点预算限制初次root清单遍历，片段递归另限128层；不是各fresh恢复器/常量
求值器所有重复遍历的总时间或内存预算。

双侧归约入口报告升级为rmsnorm-route-comparison/v2：路线贡献比较成功后，
必须fresh运行此局部检查；任一unknown/rejected阻止整体evidence。新增子检查
不解除两侧原有义务，也不把route叶值对应从unknown升级为相等。

## 两侧归约贡献与有序加法树

`verification.block_routes.compare(source, target)`要求两份完整显式route输入，
不允许省略second_offsets/shared_slots后使用默认值。它重新运行两侧贡献检查，
仅在block_threads相同时以相同tid作为条件输入叶标签；不同block不猜重分工映射。
两侧各自覆盖所有tid且恰好一次，才记录contribution_multisets_equal。

随后在共享的精确tuple intern表中构造有序加法DAG；保留每次add的左右操作数、
所有层次和显式zero seed，不做结合、交换或零消除。比较不依赖哈希碰撞假设，
也不按展开表达式大小占用指数内存。存储/同步不是该DAG中的操作节点，其语义
仍作为独立前提，不能由加法树相同推出。

`device_evidence.compare_rmsnorm_routes(source_root, source_protocol, target_root,
target_protocol)`分别fresh调用collect_rmsnorm，并将本次生成的route输入提交给
比较器；不接收旧的成功报告。结果最多为evidence，不签发整核或IEEE等价。
两侧相同tid的local accumulator值是否相等仍为leaf_value_correspondence=
not_established。全部原有未解除义务保留；源目标width用途、输入值、输出参数/
数值协议和机器码对应都不能靠本比较器补齐。

32→64可以得到贡献重数一致但有序加法树不同；这不证明浮点结果必然不同，也不
证明在冻结tolerance内。即使树相同，也仍需叶值、运算模式、源码对应与设备证据。

## 行偏移的整数部分

`verification.row_offset.check(expression, row_id, count_id, row_interval, count_interval,
integer_types)`检查完整typed表达式的符号乘积、逐节点整数范围与转换值保持。
`wavebridge.row_offset_check.check(root, kernel_id, launch_id, integer_types, row_binding,
thread_binding, int_bits=32, use_host_guard_assumptions=False)`从同AST fresh组合坐标、
列数域和两处整数偏移；host守卫假设需显式开启。示例ABI为
`examples/abi/row-offset-conditional.json`，其中long64仍是外部假设。
两接口均不证明指针加法/内存有效性、参与、浮点正确性或部署；详见协议文档。

计划建立跨执行组织的输出关系检查，包括操作、重复计数、参与条件、存储和写入义务。需要明确源有效性、数值契约、支持子集和模型到代码的一致性边界。

当前包含 Python 无界整数参考 checker、条件列覆盖/归约关系检查和整数转换检查；没有编译器级证明或真实 HIP 等价验证。

## 精确 kernel/launch 静态绑定

`verification.launch_binding.check(root, selection)`从完整单TU Clang AST重新读取
launch，不接受先前分析成功报告。`selection`采用`launch-selection/v1`，包含
`ast_root_sha256`、`kernel_declaration_id`、`launch_id`、
`configuration_declaration_id`和按位置排列的四个`configuration_expression_ids`。
这些ID仅是选点，不是值、效果或正确性oracle。

`kernel-launch-binding/v1`检查唯一kernel定义及CUDA属性、直接callee声明与
类型链、形参/实参位置、四个配置槽位的完整表达式身份；同ID冲突保持unknown，
只有同ID完整节点相同的launch重复可归一。配置声明的相同副本数量另行记录。
默认最多一百万AST节点，可显式提高至一千万；缺失工具证据或不支持形状不放行。

选定位置绑定与全TU发现分开：另一个具有不同非空ID的依赖模板launch未解析，
不自动使精确选点失败；原始未解析清单和归一记录保存在`launch_discovery`，
`complete_launch_resolution=not_established`。同ID冲突仍全局拒绝，缺ID无法
证实是另一个位置时拒绝；选中未解析位置或串用别处配置表达式同样unknown。
该范围不证明整个TU、调用闭包或其他launch都被支持。

checked仅表示这一静态配对。槽位0–3没有自动获得grid/block/shared/stream的
API语义，参数值、对象历史保持、host可达性与配置函数语义均未建立；完整AST
忠实性是前端前提。报告始终source_program_checked=false、deployable=false。
它不是GPU候选验收入口，不能替代设备关系、目标重提取或数值检查。

## 同次调用的设备整数证据包

`wavebridge.device_evidence.collect(root, protocol)`按顺序fresh调用静态launch绑定、
`row_offset_check`及`shared_storage_check`。共享支路只能使用本次row-offset调用
返回的thread子报告；不提供传入旧成功报告的接口。根、kernel/launch、ABI与
各协议哈希须匹配，前项unknown/rejected时停止依赖支路并保留原报告。

协议为`device-integer-protocol/v1`，字段为`selection`（上述launch选择协议）、
`integer_types`、`sizeof_bytes`、`row_binding`、`thread_binding`、`int_bits`和
显式布尔`use_host_guard_assumptions`。row/thread各采用原有条件协议；API轴、
leaf和ABI仍为外部前提，不能由本接口推断。开启host guard选项也不会把外部
运行时/源有效性前提变成已证明事实。

输出`device-integer-evidence/v1`。所有选定局部检查通过时状态为`evidence`，
`all_selected_integer_checks_passed=true`，不是整核checked；失败为unknown或
rejected。配置对象历史、指针有效性、参与/收敛、shared值和同步、归约值对应、
浮点输出、目标源码及设备执行义务仍显式保留。它是同次证据编排，不是新证明
算法，也不改变qdot pipeline的模型边界，不授权GPU部署。

`device_evidence.collect_rmsnorm(root, protocol)`在保持上述v1入口不变的前提下，
将其同次fresh chain/helper/indexing/capacity与fresh输出结构相连，再运行独立
XOR及block有限贡献计数。两份chain须一致；accumulator、consumer调用位置、
shared array、输入/输出/count参数以及两处已检查列循环的range/start/bound/step
逐项绑定，不接受调用者提供归约或输出成功报告。

block route的参数均显式给出：两次offset来自同一reduce声明；writer来自helper
和索引检查；gather偏移0来自已检查的index=lane；槽数来自available_bytes除以
外部float大小。barrier=True仅用于条件计数模型，表示尚未证明的全员到达与
写入可见性前提，不是barrier调用语法的推论。全部局部连接成功时输出
`rmsnorm-structural-evidence/v1`的evidence状态；output仍为recovered，route
checked仍仅为条件贡献计数。原整数包的所有剩余义务保留，尤其shared值、
shuffle对应、参与/同步、浮点与目标改写，不能据此生成已授权部署工件。

## 条件配置字段检查

```bash
PYTHONPATH=src python3 -m wavebridge.configuration_check SOURCE_REPORT.json \
  --abi examples/abi/int32-conditional.json --output NEW_CHECK.json
```

输入为 `source-column-evidence/v1` 源码报告和 `integer-abi-assumptions/v1`
外部类型表。检查器连接精确构造声明、参数位置和完整字段映射，按由内到外
顺序检查整数转换链，并要求每步保持常量值。不会按 `dim3` 或字段名字猜值。

输出 `conditional-configuration-check/v1`，绑定实际读取的输入字节与实现哈希。
每个 launch 分别检查 grid/block 构造模型；任一拒绝使整体 `rejected`，所有
非空配置均通过才为 `checked`，缺失或 symbolic 保持 `unknown`。退出码分别为
1、0、2；命令或输入错误也返回2，但不产生检查报告。输出文件必须不存在。

`checked` 仅指显式 ABI 与报告常量前提下的字段值模型。报告忠实保留 AST、
声明常量准确及 ABI 匹配目标仍是外部前提；本工具不重新验证源码/AST绑定、
host 可达性、实际运行维度或机器码。始终设置 `source_program_checked=false`
和 `deployable=false`。示例 ABI 是假设，不是设备探测结论。

### 显式区间模式

```bash
PYTHONPATH=src python3 -m wavebridge.configuration_check SOURCE_REPORT.json \
  --abi examples/abi/int32-conditional.json --use-host-guard-assumptions \
  --output NEW_INTERVAL_CHECK.json
```

此选项显式采用 `host_guard_intervals` 作为外部前提，不重新证明守卫。CLI 先
核对守卫报告状态、精确 launch ID、解释范围，以及源码报告/守卫/ABI 的整数
位宽一致性；缺失或不一致保持unknown，不能回退成通过。默认不开启此模式。

独立 `constructor_values.check(..., declaration_intervals=...)` 对符号实参
按声明 ID 和原始叶类型匹配闭区间，并逐步检查区间内全部整数是否能在转换
前后保持值。部分越界、负数转无符号、重复声明或类型链不连续不会放行。
区间表最多64项，不枚举实际范围；缺有限区间或支持类型时保持unknown。

区间模式分别输出 `constructor-values-check/v2` 与
`conditional-configuration-check/v2`。字段 `value_kind=constant` 保留 `value`；
`value_kind=interval` 只给出 `interval.lower/upper` 和声明 ID，不伪造单一值。
报告记录区间输入哈希和实际使用的声明前提。

即使 grid/block 字段域全部checked，也只说明显式域和 ABI 下的整数值保持，
不说明实际运行维度、shared容量、线程坐标、host有效性或GPU等价。部署标记
仍为false。已有v1常量模式的含义不变。

## 单个 kernel 整数实参

`kernel_arguments.check(binding, declaration_intervals, abi)` 接收源码报告中
一个 `parameter_bindings` 条目和显式域，直接遍历原始实参AST的括号/允许的
隐式转换，关联声明区间或整数字面量，检查到形参类型的整段值保持。

输出 `kernel-argument-domain-check/v1`；位置绑定的来源可信是显式前提，此
API不核实完整kernel签名，也不自行证明输入域。区间没有被改成单值；指针、
浮点、调用表达式及缺域保持unknown。即使列数参数checked，其余参数与整核
仍可能未知，不能用一个标量参数通过替代完整launch或源码等价检查。

## 条件共享容量检查

```bash
PYTHONPATH=src python -m wavebridge.shared_capacity_check SOURCE_REPORT.json \
  --abi examples/abi/storage-conditional.json --output NEW_CAPACITY_CHECK.json
```

`storage-abi-assumptions/v1`显式提供整数ABI及sizeof类型字节表；示例不是设备探测。
独立`verification.shared_bytes.check`读取launch第三配置实参的原始AST，支持非负
整数字面量、括号、值保持整数转换、sizeof(type)与乘法。所有中间值须在显式
类型范围内，缺sizeof依据、动态变量、溢出或窄化保持unknown，绝不猜float=4。

`shared_capacity.check`以同一kernel ID关联结构链和launch，按受限block模型的
`block_threads / width`计算partial槽位需求。动态shared读取launch字节表达式，
静态shared读取声明extent；不把动态分配字节数补给不足的静态数组。普通局部
数组、未建立绑定或不支持的block模型保持unknown。容量不足为rejected，足够
仅为条件checked；CLI绑定源报告/ABI文件及实现哈希，输出文件不可覆盖。

必须区分显式前提与结论：结构报告忠实于同AST、实际block与坐标匹配、共享数组
起于偏移0且无其它动态分配、配置第三参数语义、ABI、别名及参与者有效性均为
外部前提。本checker不重新证明这些前提、不验证AST绑定或硬件分配；始终保留
source_program_checked=false与deployable=false。缺launch或未解析launch时不能
全局checked。它不是一个自动部署许可，也不替代block路由或浮点数值检查。

## block字段与线程模型

`verification.block_configuration.check(chain, site, integer_types, axis_binding)`
复用独立constructor_values检查器，从site的第二个配置构造报告计算字段值，再与
`(block_threads, 1, 1)`比较。显式axis_binding必须给出同一launch ID、构造声明ID
及三个不同FieldDecl ID到x/y/z的对应；不根据名字、参数位置或线程总数推断坐标。
字段交换为(1,256,1)、多维(16,16,1)即使总数256，也会相对一维模型rejected。

axis_binding使用`launch-axis-assumptions/v1`，是外部API语义假设，不是自动恢复的研究成果；Clang ID只能用于绑定
的同一AST。API缺映射、不同kernel/launch/构造、ABI不一致或字段值未知时不能通过。
checked仅说明显式坐标语义下构造字段匹配；仍不证明kernel实际读取了x坐标、host
执行了该launch或设备采用了该配置。该API尚未自动合并到共享容量CLI或部署判断。

## getter返回链的条件值保持

`verification.getter_returns.check(root, start_declaration_id, leaf_contract, integer_types)`
从单TU原始AST独立重建函数链，不读取return_trace的成功标志或生成器自报模型。
起点可为static方法；内部只支持无形参、非variadic、单return的直接free函数调用，
返回表达式可带括号/IntegralCast。exact ID重复、算术、多语句、动态成员、递归、
超过预算或缺ABI均unknown。当前上限100万AST节点、32层调用、32层表达式。

外部协议`getter-leaf-domain/v1`明确给出`declaration_id`、`arguments`（最多4个
非负常量）、`return_type`（Clang式类型对象）、`lower`、`upper`。叶节点必须是
无函数体的非variadic FunctionDecl；其参数数/类型与实际调用对应。实参仅支持
非负整数字面量及括号/IntegralCast，逐级检查值保持后与协议常量匹配。
**ID与实参对应不意味着该函数是local-id或轴0具有x含义**；协议返回域仍是外部假设。

结果`getter-return-domain-check/v1`按叶到起点顺序检查整个区间内的返回转换。
支持域内非值保持的返回窄化为rejected；协议实参不匹配或实参转换不支持为unknown，
不是错误kernel的证明。checked返回原区间及返回类型，保留调用边、转换证据和
完整root/起点/协议/ABI的规范化SHA256。调用表达式类型与函数声明签名的一致性
仍依赖忠实、有效Clang AST，不宣称重新验证了编译器类型系统或完整C++签名。

该API不证明外部函数语义、输入区间真实性、初始化表达式/属性receiver纯度、
launch域或源/目标等价。source_program_checked/deployable始终false。尚无独立CLI，
本身不与value_link或block配置自动组合；不能据此放行GPU候选。组合API见下一节。

## 初始化域与选定launch的线程起点组合

`device_evidence.compare_rmsnorm_local_values(source_root, source_protocol,
target_root, target_protocol, assumptions)` 是独立的条件抽象值入口；内部重新运行
v5，不接受旧检查报告。`paired-local-input-assumptions/v1` 使用严格键集：
`source/target` 各绑定 root/protocol SHA256、kernel/launch ID 和 input/count 参数
ID；三个 `*_assumed`（common_count_and_coordinates、same_immutable_logical_input_array、
valid_complete_local_executions）必须为 JSON true；`coordinate_domain` 必须是
`common_tuple_in_both_checked_domains`，`input_origin` 必须是
`kernel_entry_parameter_before_row_offset`，`evaluation_model` 必须是
`common_total_deterministic_order_preserving_typed_AST_interpretation`，另须非空
`evidence_reference`。多余的 output/accumulator equality 字段也拒绝。

共同坐标是对两侧 checked 域内共同 r/n/t 的全称条件，不是已测得的执行配对。
共同逻辑输入假设要求：以进入 kernel、尚未执行行偏移的参数为原点，在坐标/
前缀求值至最后一次局部 load 期间，对应元素值相同且不变，包含 alias/其他
线程/并发写的影响；load 和局部执行有效。运算解释是相同、全定义、确定性、
保持 AST 顺序的抽象解释，不推断实际 rounding、FTZ、NaN、异常、FMA 或重排。
完整 typed seed/loop 与检查过的有序索引相同，才能用迭代归纳得到抽象 loop-exit
accumulator 的条件对应。结论不是 C++ `==`、bitwise IEEE 等价或编译后行为证明；
顶层实际叶值对应仍未建立，shared reduction、输出及部署保证不升级。

双侧 v5 新增 `load_index_relation`：消费同次 fresh 局部恢复、唯一 range 匹配
的 column recovery/coverage、行偏移、坐标和 v4 effect 结果。要求正整数
loop step 等于已检查 block x，角色 ID 一致，源偏移为已检查的 row*count。
在共同 `(r,n,t)` 位于两侧相同域的假设下，比较有序规范式
`r*n+t+k*B`、`k>=0`、`t+k*B<n`。这不是基于少量输入的枚举接受。
结论仅针对相对各自 input 参数基址的逻辑元素下标；地址有效性、运行配对、
input 对象/内容、并发修改、执行参与及 FP 保持外部义务，不升级 leaf 标记。

双侧入口 v4 要求每侧协议提供 `coordinate_effects`，且仅含 `row`、`start`。
每项包含现有 `effect_protocol`（getter-leaf-effect-assumption/v1）与
`receiver_protocol`（property-receiver-assumptions/v1）。不接受旧成功报告。
入口从本次 fresh row/thread 结果选择精确 property ID 和已建立的 leaf 域，
重新调用 `check_property_no_memory_write`；缺失、过期、错接或超子集即 unknown。
当前只支持受限 PseudoObjectExpr 路径；不是通用 C++ 调用副作用分析。
外部 leaf 无写入/正常返回、receiver 初始化/存活和扩展语义仍是 unverified
假设，不能由 effect 的 checked 状态宣称已经验证 SDK 或完整初始化历史。
外层整数转换仍由既有 initializer/domain 路径检查；这里不包含变量初始化
写入本身，也不证明运行实参、指针内容或叶值等价。旧协议缺少此字段时 v4
保持 unknown；旧版结构证据记录不因此变成错误的历史数值结果。

双侧 `device_evidence.compare_rmsnorm_routes` 的 v3 还将 fresh 局部计算模板
同本次 row/thread/prefix 证据连接。局部恢复结果必须与前缀内的同一恢复结果
完全一致，input/start/bound/accumulator 精确绑定，再比较两侧条件入口关系
签名。缺证据、角色错接、不同区间或 ABI 均不能沿用已有 route evidence 放行。
这里的 evidence 仅是结构/条件关系，不是运行实参或指针内容相等；报告显式
保留两侧 host guard 模式，签名相等不声称两侧前提集合相等。

坐标值组合只支持 kernel 直接块作用域中唯一的普通自动 `const int` 声明。
`static`、TLS、未知声明属性、全局或嵌套作用域起点保持 unknown；初始化调用
结构存在，不意味着本次 invocation 执行了该初始化。行前缀的 row/start 同样
限制为自动存储期。`declaration_evaluation` 只描述声明每次被经过时的初始化
规则，不证明 getter 无副作用、跨源码入口值相等或实际设备执行。

`verification.initializer_domain.check(value_link, getter_report, integer_types)`
在可信前端value_link与真实getter检查证据前提下，核对callee/start ID、call结果
类型及getter的ABI hash，再从内到外检查最多32级初始化IntegralCast。它不重新
解释pseudo-object或证明receiver纯度；缺失/不匹配保持unknown，确切窄化为rejected。
结果为`initializer-domain-check/v1`，只在checked时给出完整结果区间。

`thread_start_check.check(root, kernel_id, launch_id, integer_types, binding, int_bits=32)`
是**源码恢复与检查的组合层**，不是新增独立前端。它不接收旧的成功报告，而从
同一原始AST重新恢复列循环、归约链、launch配置、构造字段与初始化结果调用，
再执行block配置、getter返回和初始化域三个检查。前端仍属于可信基础。
支持所有已恢复列循环共用一个声明起点，且步长等于已恢复block线程数。

外部`thread-start-assumptions/v1`必须绑定规范化`ast_root_sha256`、kernel ID、
launch ID，并提供已有`launch-axis-assumptions/v1`的`axis_binding`及`coordinate`：
`semantics=workgroup_local_id`、`axis=0`、外部函数`declaration_id`和`return_type`。
还须显式声明`configuration_positions={grid:0,block:1}`，其它位置不支持。
这些是外部API协议，不是按名称推断的发现；旧AST的ID/绑定不能复用。
getter的[0,block.x-1]区间由已检查block配置与该外部local-id语义共同导出，
不另填人工线程区间。三项通过后才返回`conditional-thread-start-check/v1`的checked。

结论仅覆盖**这个选定launch的列循环起点**在显式API/ABI/有效源码/运行配置前提下
等于local x；不覆盖其它launch、归约helper内其它坐标读取、所有线程参与、内存、
浮点等价或外部实现本身。嵌套checker的premises保留；block checker只检查配置
与一维模型相符，不再预设kernel起点使用x，避免将待证结论作为自身前提。
source_program_checked/deployable始终false。当前是Python API，无自动部署或CLI。

## Helper 的逐线程 group/lane 分解

`verification.index_partition.check(expression, coordinate_expression, width_declaration_id,
width, block_threads, integer_types, operation=...)`枚举最多1024个线程，逐点核对
完整初始化表达式是否为`t//width`或`t%width`，不以输出范围相等替代关系相等。
表达式最多128节点/32层，须含一个完整AST相等的坐标锚点；支持非负整数字面量、
精确宽度声明引用、括号、允许的整数转换和除/余运算。逐节点核对显式ABI和
转换值保持，坐标或宽度含义仍是外部前提。结果`index-partition-check/v1`只描述
该模型上的逐点关系，窄化/错误分解可rejected，不支持/缺证据为unknown。

`block_coordinate_check.check(root, thread_report, integer_types, binding)`是组合层。
要求真正的`conditional-thread-start-check/v1`成功证据，并重新核对root、ABI、
协议hash与kernel/launch；hash绑定不是证据真实性认证。随后从原AST重新发现
已连接的block helper，核对其width/block与线程报告的关系链一致。

group/lane的两个坐标表达式分别重新建立结果调用连接，并检查同一外部local-id
协议和域下的getter/坐标转换；然后将原始完整初始化式交给逐点分解checker。
返回`conditional-block-coordinate-check/v1`，只证明显式协议下这两个初始化式
分别等于local_x/width和local_x%width。该范围不证明其它cast、writer谓词、
参与收敛、shared索引访问、同步、shuffle路由或浮点等价。API语义在helper内
仍成立、源码有效性及实际launch配置继续是前提，不签发source_program_checked
或deployable。前端恢复仍属于可信基础，不能宣称独立验证了全部编译器。

## 选定 launch 的整个列数域

`column_domain_check.check(root, thread_report, integer_types, binding,
use_host_guard_assumptions=True)`重用真实线程起点证据并校验同AST/ABI/协议hash。
从原AST重新恢复列循环、选定launch的形参位置绑定及host提前返回的必要条件域，
通过kernel_arguments核对列数实参的整数转换，再调用独立区间覆盖checker。
必须显式启用host guard假设；默认unknown。当前仅支持直接位于kernel body的
ForStmt、共同const线程起点、常量步长等于线程数，以及只发生读取的列数形参；
形参赋值/取址/引用逃逸、嵌套或有早退的上下文保持unknown。

`verification.column_coverage.check_interval(lower, upper, starts, stride, int_bits=32)`
利用固定起点/步长下小列数的迭代序列是上界序列前缀的性质，只检查一次上界，
不枚举整个列数域。上界的完整覆盖、无重复和末次循环增量无溢出可推广到闭区间；
上界rejected提供域内反例，溢出或不支持保持unknown。

`conditional-column-domain-check/v1`的checked仅说明每个列索引在模型线程间
恰生成一次，并非循环体每列恰贡献一次。guard域是必要条件过近似，不证明每个值
可达，也不替代外部合法输入/数值协议。线程均正常到达循环、有效源码、可信前端
与外部API/ABI/实际launch仍是前提；不检查数组访问、别名、归约、同步或浮点值。
source_program_checked/deployable始终false。当前为Python API，不提供部署许可。

## 共享写入与收集的整数关系

`verification.shared_indexing.check(access_asts, bindings, width, block_threads, integer_types)`
以已建立的group=t/width、lane=t%width及宽度/block常量含义为条件，逐线程检查
完整writer/gather谓词与活跃分支下标。目标关系为lane==0写group槽，lane<group数
读lane槽；inactive分支不执行下标表达式。显式ABI下的整数转换必须值保持，不能
以剥除转换后的结构相同代替。谓词的bool结果遵循语言逻辑值，不猜测bool存储ABI。

`shared_index_check.check(root, thread_report, integer_types, binding)`先从同AST重新
运行block_coordinate_check，再将fresh helper中保留的四表达式交给该checker。
结果`conditional-shared-index-check/v1`仅连接坐标与这些整数关系；不证明shared
指针/容量/别名、存储值、barrier或shuffle语义、参与收敛及浮点结果。线程到达
这些阶段及所有上游API/ABI/源码有效性前提仍需成立，不授权GPU部署。

## 同AST数组绑定与容量组合

`shared_storage_check.check(root, thread_report, integer_types, sizeof_bytes, binding)`
先fresh运行shared_index_check，再从原AST重新恢复归约调用链、shared数组实参和
选定launch。组合门控核对kernel→helper精确ID、width/block一致，以及数组绑定的
parameter_id确实为已检查下标所用helper的shared形参；不拼接旧容量成功报告。
随后由shared_capacity检查实际静态extent或选定launch的第三配置实参字节数。

报告`conditional-shared-storage-check/v1`保留indexing、chain_recovery、capacity。
输入绑定由input_sha256和sizeof_bytes_sha256共同组成，两者都须保留。结论仅为
该条件模型的整数下标与对应数组容量，不证明独占动态shared布局：单数组、偏移0、
无其它动态分配继续是显式前提。第三配置实参的API含义、真实ABI、源有效性、同步
与参与也仍需成立。source_program_checked和deployable均false，不能把容量组合
checked写成“完整内存安全”。

## 入口前缀的有限递推上界

`column-coverage-interval/v1`成功报告新增max_iterations_per_thread和max_iterations，
在整个声明列数区间上分别给出每线程body执行次数及其最大值。计算依据是固定
正步长、起点、列数上界，且已检查最后一次增量不溢出；不证明body正常返回。

`entry_loop_check.check(root, thread_report, integer_types, binding,
use_host_guard_assumptions=True)`fresh运行列域检查和归约链恢复，按精确call绑定
及唯一loop range把entry_control义务关联到迭代上界。没有prefix loop或不能唯一
关联则unknown。输出`conditional-entry-loop-check/v1`的checked只表示有限递推
次数，不表示kernel入口可达或所有线程进入helper。上游列域的“线程到达循环”
前提仍保留，不能循环使用本报告去证明该前提。body_normal_completion保持
not_established，remaining_call_obligations原样保留，participation未建立。

## 前缀 getter 的条件正常返回

getter_returns成功报告的completion记录精确外部叶、实参及有限调用边数，表示
受支持的无环单return整数调用链在外部叶正常返回、调用有效的前提下正常返回。
它没有证明叶函数终止、receiver有效性或调用点初始化表达式完成；其它状态不带
此结论，也不能从整数值保持失败推出不终止。

`entry_call_check.check(root, kernel_id, int_bits, integer_types, protocol)`fresh恢复
入口控制义务，再逐项运行getter checker。协议`getter-completion-assumptions/v1`
须显式提供ast_root_sha256、kernel_declaration_id、external_normal_return_assumed=true
及getters映射（每个起点声明ID对应getter-leaf-domain/v1）。不按函数名补全协议。
缺少任何getter契约、body检查不支持或值保持失败，整体unknown并保留局部结果。
`conditional-entry-call-check/v1`只覆盖callee body；调用点receiver/实参求值、
循环body有效性和helper可达性仍未建立，participation/source/deploy均不升级。

## Grid 配置域

`verification.grid_configuration.check(site, integer_types, axis_binding, declaration_intervals)`
检查第0个配置构造式，在显式FieldDecl ID→轴映射下将常量/符号字段归一化为区间。
只有x全域为正且y/z恒1才checked；域内反例不代表该值实际可达。不按名称猜轴，
不猜硬件grid上限，也不自动赋予block-id语义。

`grid_domain_check.check(root, kernel_id, launch_id, integer_types, binding,
int_bits=32, use_host_guard_assumptions=True)`fresh恢复选定launch、构造字段与host
guard。`grid-domain-assumptions/v1`显式绑定root hash/kernel/launch、
configuration_position=0及已有launch-axis-assumptions/v1。输出
`conditional-grid-domain-check/v1`保留必要条件域证据；不证明域可达、实际运行
配置或设备launch限制，不授权部署。与block-id连接仍需外部API语义协议。

首例采用[HIP 7.1.1 index built-ins协议](https://rocm.docs.amd.com/projects/HIP/en/docs-7.1.1/how-to/hip_cpp_language_extensions.html#threadidx-and-blockidx)，
配合固定SDK头文件与精确getter AST调用链，把已检查grid.x上界减1作为外部
group-id叶值域上界。该组合目前在诊断runner中完成，不是通用自动API识别器，
也不证明外部叶实现或正常返回。来源与文件hash见对应交接。

## 从 grid 域到 row 初始化式

`row_coordinate_check.check(root, kernel_id, launch_id, integer_types, binding,
int_bits=32, use_host_guard_assumptions=True)`fresh运行grid域和row-prefix恢复，
从源码row_initializer_evidence取得结果getter，再检查其返回链与初始化转换。
外部`row-coordinate-assumptions/v1`绑定root hash/kernel/launch，内含grid_binding
及coordinate（semantics=workgroup_id、axis=0、精确外部叶ID与返回类型）。
没有人工row声明ID或人工row上界；上界从已检查grid.x域的upper减1得到。

`conditional-row-coordinate-check/v1`的checked只在外部group-id/ABI/实际launch
语义前提下确认row初始化式等于workgroup x，并输出跨grid域的row_interval。
值保持失败保留rejected，缺协议/不支持保持unknown。该区间不是每次launch的
精确行集合，也未保持row与动态nrows的完整相关性；不得直接用它替代逐输入内存
边界证明。不检查指针偏移、分配大小、别名、参与或FP结果，source/deploy为false。

## 坐标循环体的条件保持检查

`verification.column_body.check(root, function_id, loop_id, integer_types,
property_protocols, binding, *, max_ast_nodes=None)` 从完整 TU 选择唯一函数和
唯一循环；第一子集只支持函数体直接包含的坐标型 ForStmt。fresh 观察 header，
推导 induction、边界参数和起点/步长 receiver 的受保护声明，不接受人工保护列表。
循环体须为 CompoundStmt，每个循环检查 1～8 个属性表达式；超出保持 unknown。

`binding` 的版本为 `column-body-assumptions/v1`，精确绑定 `root_sha256`、
`function_id`、`loop_id`；`source_validity_assumed` 与
`no_alias_with_protected_declarations_assumed` 必须为 true，`evidence_reference`
非空。这些是外部前提，引用本身仍 unverified。

`property_protocols` 按 body 内原始 PseudoObjectExpr ID 提供 `leaf_contract`、
`effect_protocol`、`receiver_protocol`。每项重新执行属性 receiver/getter 检查；
缺失、多余、错绑定或调用方自报 checked 不可代替检查。只有该属性完整通过，
body 遍历才将其视为已检查子树；其它节点继续使用原存储目标与副作用限制。
默认源码恢复入口不因此放宽。

checked 仅表示在这些前提下，选定 body 保持受保护变量；合法的输出数组写入和
局部累加仍可存在，所以不是整个 body 无写。它不证明 header 的实际坐标含义、
每轮 getter 值稳定、转换/增量无溢出、列覆盖、正常完成、浮点结果或整核正确性，
不接通部署门控。预算按每次完整扫描约束节点数，不是总时间或内存预算。

## 动态构造实参中的整数选择

`verification.integer_selection.check(root, expression_id, declaration_intervals,
integer_types, *, max_ast_nodes=None)` 独立核对完整 TU 中一个原始值表达式。
输入域条目为 `{declaration_id, type, lower, upper}`，必须精确匹配使用的声明；
缺失、重复、错类型或不可表示域不能检查通过。ABI 使用既有 `bits/signed` 格式。

当前只接受两个 const 内建整数引用参数、单 return 的 `<`/三元选择函数，以及
立即 LValueToRValue 读取的直接调用；实参限普通整型声明和 full-expression
字面量临时对象。声明按 ID 关联，函数名、参数名不携带数值语义。
外围 IntegralCast 检查整段结果域的值保持；不是按截断/取模解释窄化。

报告 `integer-selection-check/v1` 绑定 root、表达式、输入域和 ABI 哈希，并记录
callee、选择方向和相等时分支。结果只表示显式域下的 minimum 值区间，
不建立返回引用身份保证、外围清理、域来源、构造字段、命名对象复制或 launch
前值保持；也不把既有 constructor_arguments 的 unknown 自动升级。

## 从原始构造表达式组合字段域

`constructor_source_check.check(root, expression_id, integer_types,
selection_domains, *, max_ast_nodes=None)` 接收完整 TU 中直接构造表达式的 ID。
它重新恢复构造身份、实参和完整字段映射，再独立检查每个受支持实参。
`selection_domains` 为 `{argument_expression_id: declaration_intervals}`，只提供
外部变量域，不接收或信任调用者自报的 `checked`。键须精确覆盖需要检查的动态实参。

第一子集为整数字面量（含有源码关联的默认实参）和已支持的 minimum 调用。
动态实参从原始完整表达式重新运行 `integer_selection`，不会用伪造字面量或
虚拟 DeclRef 替换 AST；其完整转换已经检查，之后只连接形参类型及字段初始化
转换。字段按精确 ID/参数位置关联，不按 x/y/z 名称猜测坐标轴。

输出 `source-constructor-values-check/v1` 仅在全部字段义务满足时给出 checked。
签发字段域前还会从同一完整 TU fresh 运行 `constructor_effects`，核对构造器和
所属 record 的精确身份。不能仅凭 `FieldDecl.type=unsigned int` 把 bitfield 当成
完整 unsigned 存储；bitfield 等不支持存储形状保持 unknown，不输出字段域。
报告保留副作用子报告，但 `call_argument_effects` 和 `post_construction_escape`
仍为 not_established；组合接入不等于整个调用或对象历史已经验证。
真实 TLS 回归展示这一边界：minimum 的整数结果和字段域可以正确，但首次使用
动态初始化的 `thread_local int` 仍可能写入其他存储。Clang JSON 的存储期证据
包含 `tls: dynamic`；未来参数效果门控不能只检查类型或 `tlsKind`，还需检查
声明作用域、初始化、属性和捕获路径。现有值域前提不替代这些效果证据。
原始恢复报告保留 unknown 等真实状态，组合结果不会回写成 inspected。
结论只覆盖构造求值时的条件字段域；输入域来源、清理、复制、后续写入和实际
launch 对应仍未建立。默认既有报告检查入口及部署门控不改变。

## 复制求值时的整数字段关系

`record_copy_check.check(root, expression_id, integer_types, *, max_ast_nodes=None)`
从完整 TU 重新关联直接复制表达式的实际构造函数、所属 record 与源声明。
第一子集为同一 record 的 const 引用参数、空构造函数体、全部直接内建整数
字段逐一从该参数的同一 FieldDecl 读取。不根据 implicit/noexcept 标签或类型名
猜测复制语义；手写复制必须满足同样的源码条件。交换字段、额外写入、不完整
初始化以及 union、base、bitfield、volatile、指针等不支持情形不能通过。

`record-copy-check/v1` 的 checked 只表示复制求值时对应字段的值相等，不给
数值域。`source_declaration_id` 只记录词法 DeclRef 绑定，不证明运行时源对象
身份（例如按值 lambda 捕获）；`source_declaration_binding=lexical_declref_only`、
`source_object_identity=not_established` 明确保留这一缺口。关系针对实际求值的
复制实参，不能据此跨越捕获边界。`field_mappings` 记录精确源/目标
FieldDecl ID；`source_object_preservation` 和 `launch_semantics` 始终未建立。
即使源对象在初始化之后被修改，合法的逐字段复制仍可以通过这条局部关系检查；
不能据此搬用初始化时的字段域。源对象存活、字段有有效值、AST 和 ABI 可信仍是前提。

同一非空表达式 ID 若在 AST 出现多次，只有完整节点一致才归一；记录
`expression_ast_occurrences`，不解释为执行次数。冲突副本拒绝，不同 ID 不合并，
声明/record/形参唯一性不放宽。旧构造字段检查和部署门控不因此改变。

## 全引用捕获链的条件对象身份

### 独立结构入口与条件接口的区别

`capture_source_check.inspect_structure(payload, copy_expression_id, integer_types,
*, max_ast_nodes=None)` 不接收生命周期协议，也不调用条件字段值或条件身份检查。
它fresh检查复制构造器的受限结构效果，复用共享的捕获路径解析，核对原生
by-reference边、全部立即receiver祖先，以及source与copy所在的同一普通函数body。
报告为`capture-source-structure/v1`；具名、传出、返回closure及不支持的效果
仍unknown。它不签发动态对象身份或值保持结论；没有假设alive再删除报告前提。

这里的checked只描述可信AST/原生元数据中的声明和路径绑定。source lifetime、
历史值保持、调用可达性、其它调用或清理效果及部署均未建立；不能用此结果单独
解除alive。`copy_structure`及独立的`activation_binding`保留来源，不使用
`identity_completion`将结构包装成动态保证。
立即调用子报告仍保留其原有有效执行前提；本入口只消费静态ID与祖先路径绑定，
不把其中的条件receiver身份升级为已执行、已存活或动态对象身份保证。

旧`check`继续消费原v1/v2/v3协议，在共享语法解析之后添加条件动态身份结论。
v1仍允许外部声明的具名closure来源；旧值路径对未支持效果属性的容忍不变，
可能出现条件值checked、独立结构unknown。新入口的严格范围不能反向缩窄旧协议。

`capture_source_check.check(payload, copy_expression_id, integer_types, protocol,
*, max_ast_nodes=None)` 消费同次原生 envelope，fresh 运行复制检查，再从完整 AST
重新恢复目标表达式的 lambda body 路径。它跳过 closure record 内的重复 body，
捕获初始化式按外部路径处理；相同 ID 的冲突节点或不同路径不能归一放行。

首个子集要求普通非模板函数内、所有相关 lambda 之外的自动非引用 VarDecl。
每层必须有唯一正面原生捕获记录、精确 closure/field/initializer 声明关联和
匹配的外层路径；只接受全 by_reference 链。缺失记录不是“没有捕获”的证明。
按值层、static/TLS、引用别名、init-capture、generic/template 和不支持的作用域
保持 unknown；这不是判定原程序错误。

`capture-source-assumptions/v1` 必须精确绑定 root_sha256、copy_expression_id、
source_declaration_id，并提供以下严格 true 前提和非空 evidence_reference：

- source_initialized_alive_assumed
- closure_instances_from_recorded_lambdas_assumed
- source_and_closures_share_recorded_activation_assumed
- source_program_valid_assumed

这些是外部前提，不是本模块检测出的事实；引用记录保持 unverified。
checked 仅在这些条件下表示复制实参的 lvalue 指向对应的同一动态对象，
不证明其值自初始化后未变、lambda 会执行、实际 launch 或机器码正确。
复制子报告保留原有 identity=not_established，新增条件结论单独记录，不回写升级。
原生捕获元数据仍是可信前端的一部分，不宣称独立验证了 Clang API。

## 构造器实现的受限副作用检查

`verification.constructor_effects.check(root, constructor_id, integer_types,
*, max_ast_nodes=None)` 从完整 TU 独立关联唯一构造器及所属 record。
只支持普通内建整数字段、整数值参数、空函数体，以及逐字段恰好一次的参数或
字面量初始化；允许列明的整数隐式转换，但不据此证明数值保持。引用、指针、
volatile、bitfield、base、union、虚函数、调用及不支持的 AST 效果保持 unknown。

`constructor-effects-check/v1` 的 checked 仅说明该构造器成员初始化式和函数体
没有观测到目标地址读取/发布或其他存储写入；允许的写入是目标直接字段初始化。
它不覆盖调用参数求值、目标分配/生命周期、清理、异常、析构及后续逃逸。
即使构造器本身通过，`PlainValue source(publish_argument(&source))` 仍可在参数
求值时发布地址；真实 CPU 回归覆盖这一界限。不能据此将初始字段域转移到 launch。
完整有效 AST、匹配 ABI、有效参数和正常返回仍是前提；整核和部署标记保持 false。

## 受限构造参数求值效果

`verification.constructor_argument_effects.check(root, constructor_expression_id,
integer_types, selection_domains, *, max_ast_nodes=None)` 从完整 TU fresh 运行构造
字段域检查，并额外检查参数求值的声明来源与效果边界，不接受调用者提供的成功报告。
只支持普通非模板函数中的直接构造，参数为既有受支持字面量/default 或 minimum
表达式；minimum 的变量操作数必须来自同一普通函数的自动局部变量或形参。
global、static、extern、TLS、捕获/引用来源及未知属性保守返回 unknown。

普通变量早先初始化可以有副作用，成功结论不覆盖那段历史；本次绑定 const 引用
和物化内建标量临时对象则是受支持求值的内部操作。检查不宣称完全没有存储写入，
按值整数参数自身的存储初始化也不属于外部存储写。检查限制的是本次参数求值
对外部存储的写入及地址逃逸。构造器本体、目标分配、外围
清理、异常、析构、后续历史和实际 launch 仍不属于这项结论。

callee 属性只允许明确列出的形状。`enable_if` 在 Clang 中属于非运行时求值
上下文；首版只接受实际案例中的单个常量真布尔字面量形状，不开放任意属性。
语义依据见 [Clang enable_if 文档](https://clang.llvm.org/docs/AttributeReference.html#enable-if)。
数值子报告不回写升级，外部输入域、ABI、有效源码及正常返回仍是前提。

## 自动对象初始化完成时的条件关系

`verification.object_initialization.check(payload, variable_id, integer_types,
selection_domains, *, max_ast_nodes=None)` 接收同次原生 envelope（不是外层采集报告），
按唯一 VarDecl ID 关联普通非模板函数中的自动对象、直接构造式及可选的一层
ExprWithCleanups。允许普通嵌套块，不支持 static/TLS、引用、volatile、属性、
lambda 内对象或不支持的初始化形状。类型与表达式身份必须精确对应。

有清理 wrapper 时，要求同 ASTContext 的唯一原生观察精确绑定 wrapper 和构造式，
副作用标志严格为 false、辅助对象数严格为整数0，覆盖/计数语义必须匹配；若 JSON
本身带有标志，也必须一致。数量不是析构次数，标志属于可信前端证据，不是独立证明。
缺失、冲突、重复或额外清理形状保持 unknown；不会从旧工件缺字段推断没有清理。

随后从同一完整 AST fresh 运行参数效果、构造器实现与字段域检查。报告
`object-initialization-check/v1` 的 checked 仅在有效源码、匹配 ABI、外部输入域及
构造正常返回前提下，给出初始化完成时的字段域，以及该段初始化未观测到目标地址发布。
保留子报告原有边界，不信任生成器或调用者提供的成功结果。

早先别名、初始化后的值保持/逃逸、析构、异常展开、动态调用历史和实际 launch
仍未建立；`source_program_checked=false`、`deployable=false`。这不是把初始化
字段域直接传给 GPU launch 的许可。预算约束每次扫描的节点数，不是总运行时间。

## 立即调用 lambda 的接收者绑定

`verification.lambda_invocation.check(root, lambda_id, *, max_ast_nodes=None)`
从完整 AST 检查原始 lambda 临时对象是否沿受支持包装链，直接成为无参
`CXXOperatorCallExpr` 的接收者。callee 必须精确关联该 closure record 的非模板
`operator()`，其 body 与 LambdaExpr 的 body 一致；不根据相似名称猜测方法身份。
具名 closure、返回或传递 closure、泛型、带显式/默认参数、间接或显式成员调用
不在首个子集内。closure body 的重复 AST 副本必须一致，不能吞掉冲突。

这里检查的是条件接收者身份和调用语法关联，不保证调用可达、次数、正常返回、
捕获初始化/函数体/外围清理没有副作用，也不证明被捕获对象值保持。尤其
`[&]() { source.x = 99; Config target(source); }()` 可以具备正确的接收者绑定，
但复制值显然不再等于初始值。初始化、捕获身份、调用绑定三个局部成功不能
替代源对象从初始化到复制点之间的效果分析。整核和部署标记仍为 false。

同 ID 副本比较只归一化 `loc`/`range` 中的 `line` 显示字段：真实 Clang17
在重复 body 的一份 JSON 中省略该字段。节点 ID、offset、file、col、tokLen、
类型、操作及子结构仍比较；完整 root 哈希仍绑定所有原始位置元数据。

## 整函数显式源对象引用的闭合检查

### 不依赖alive协议的结构组合

`verification.object_use_closure.inspect_structure(payload, variable_id, integer_types,
initialization_selection_domains, *, max_ast_nodes=None)` 不接收capture协议，直接复制
调用`record_copy_check.inspect_effects`，捕获内复制调用`capture_source_check.inspect_structure`。
与旧条件入口共享语义遍历和引用分类，不维护另一套可漂移的引用清单。它不能
通过伪造alive协议后调用旧接口来建立结构结论。

`object-explicit-use-structure/v1`的checked只说明完整受支持显式引用与复制/捕获
结构闭合；`copy_structures`、`capture_structures`保存fresh子报告。
`conditional_initialization`仍保留有效构造正常返回前提及conditional completion；
其字段域不代表初始化实际发生，更不代表之后仍存活。立即调用子报告的动态
receiver结论、对象边界子报告的执行前提同样不能被提升为本入口的动态保证。

`source_order`、`source_reference_use_effects`、`copy_cleanup_observations`仍有独立
状态；父checked不等于这些子项全部checked。引用写入/逃逸和不支持的复制效果
使结构闭合unknown；没有显式源引用的opaque调用、其它作用域清理、可达性、
source lifetime与历史保持仍未建立。即使不可达分支的结构可检查，也不声明执行。
旧`check`保留原协议和较宽的条件值范围；真实诊断属性可使旧接口checked而新
结构接口unknown，不从属性名称猜副作用，也不因此收窄旧接口。

`verification.object_use_closure.check(payload, variable_id, integer_types,
initialization_selection_domains, capture_protocols, *, max_ast_nodes=None)`
首先 fresh 检查自动对象初始化，再遍历完整所属普通函数的语义 AST，包含所有
分支与 lambda body，不只包含某个选定复制点。重复 closure body 副本须核对，
不能由省略遍历掩盖同 ID 的源引用冲突。内联汇编属于不支持形状。

每个显式源 DeclRef 必须归入精确 native by_reference 捕获初始化，或 fresh
检查通过的直接 record copy 参数。普通复制调用 `record_copy_check`；lambda
内复制调用 `capture_source_check`，其外部协议字典的键必须恰好覆盖全部此类
复制 ID。native 捕获集合还必须与这些复制的完整 capture chain 并集一致。
所有相关 lambda 都 fresh 核对立即调用接收者。写字段、取地址、引用别名、
按值/init-capture、具名或传出 closure 等不能通过。未知不被解释成源码错误。

`object-explicit-use-closure-check/v1` 的 checked 只建立完整受支持显式引用集合
的闭合分类，并保留每个子检查的条件；不建立历史值保持、无先前别名、一般调用
纯度或未跟踪内存效果。没有显式源引用的不透明调用可以存在，其效果仍未知。
初始化字段域不能因此直接搬到复制点或 launch。失败时保留已经运行的子报告，
不接通部署门控；默认资源上限仍是各次 fresh 扫描的节点数而不是总耗时。

## 可选 canonical JSON 哈希路径

共用 `verification.integer_selection._hash` 的检查器默认保持流式编码。
显式设置 `WAVEBRIDGE_JSON_HASH_MODE=one-shot` 可改用一次性 `json.dumps`；
`streaming` 也可显式设置。其他值（含空字符串）产生错误，不静默回退。
两种路径使用相同排序、紧凑分隔符、ASCII转义与禁止NaN规则，模式不改变摘要。
它不是缓存，也不接受调用者预先计算的成功结论；其他独立哈希实现不受此选项影响。

one-shot会分配完整字符串与UTF-8字节缓冲区，仅适用于已评估内存预算的运行。
`MemoryError`不自动回退。实验记录应单独保存所用模式；固定工件上的编码耗时
不能当成完整checker或GPU加速比。未知模式在部分上层被转为unknown，在其他
入口可能直接抛错；均不签发通过，当前不承诺统一的错误接口。

## 复制构造的局部访问效果

`record_copy_check.check` 的原 `record-copy-check/v1` 主status继续只描述字段
整数值关系。`inspect_effects(root, expression_id, integer_types, *, max_ast_nodes=None)`
新增独立 `record-copy-structure/v1` 入口，与值检查共用私有结构解析器，但不调用
值检查，也不以值关系成功为前提。它要求构造声明、参数、字段、record属于更窄
的效果子集；不支持的效果使其主状态unknown。字段映射只标记
`direct_same_field_read_initializer`，不签发字段值相等结论。
构造仅允许无子节点的CUDAHostAttr/CUDADeviceAttr；未知属性、参数默认值或
参数/字段子节点、record直接属性、deleted/invalid标志均不能建立效果分类。
这不是宣称这些属性都有副作用，而是未解释的语义不自动当作无效果。

局部报告只分类AST角色：经源参数读取直接整数字段、经目标初始化对应字段、
未观测到选定const-reference绑定以外的地址发布。引用绑定本身仍是地址使用。
源/目标动态存储是否重叠、并发/先前别名、外围清理和析构、目标分配与生命周期
尚未建立；因此它不证明源内存不变，也不能将初始化字段域直接搬到复制或launch。
结构分类仅依赖忠实完整AST与外部整数ABI，不要求源活跃、字段可读或正常返回。
值检查在同一次fresh结构解析后另加这些动态前提，才签发条件字段值相等结论；
未知属性仍可出现值关系checked、局部效果unknown，保持原接口的支持范围。
现有capture/use-closure消费者只保存该子报告，没有自动解除历史保持义务。

## 包围复制点的原生清理观测

独立入口还提供`preceding_expression_cleanups`：在fresh `source_order`成立后，
逐copy选取源声明之后、在共同CompoundStmt的较早分支中的`ExprWithCleanups`。
它复用祖先检查的native wrapper/subexpression精确绑定、count及布尔标志检查。
源初始化、copy祖先wrapper、源声明前/域外以及词法较晚项分别记入exclusions，
并保留相关独立义务；排除不是宣称它们已通过。缺metadata、错绑、native副作用
标志true或无法按CompoundStmt排序的分叉保持unknown。

“preceding”只指`lexically_earlier_semantic_subtree_not_runtime_cleanup_order`。
例如未调用lambda里的wrapper可以被保守选入；不同调用实参、if/else分支或
lambda创建与body之间不按AST child顺序猜测执行顺序。两个copy分别建立选择
关系，不共享一个含混的全局前缀。即使子项checked，执行可达性、全部析构覆盖、
其他作用域清理、callee效果及源值保持仍未建立；有限native标志不成为完整效果证明。

独立`inspect_structure`另提供`local_record_cleanup_scopes`子报告，消费同次
native局部record元数据并核对精确VarDecl、直接DeclStmt/CompoundStmt、完整
record及直接析构声明。变量到record的类型关联仍是明确的可信前端假设，不是
独立类型检查。析构属性必须得到AST definitionData的正面佐证。

分类区分包围复制点作用域中较早/较晚的声明、与复制同一声明语句，以及最近
共享CompoundStmt下较早/较晚的互不包含作用域。`same_declaration_statement_as_copy`
不建立语句内顺序；`lexically_earlier_disjoint_scope`不代表该分支实际执行或
其析构必定发生。无法建立直接结构次序时子报告unknown，父结构状态不升级它。

`checked`仅覆盖元数据中已观测且属于所选函数的条目分类。清单完整性、实际
析构执行/效果和源值保持均not_established；空清单同样不代表没有清理。缺字段、
重复ID、错误作用域/析构绑定、非自动或其他不支持声明均保持unknown。旧条件
`check`接口不新增此项，也不改变其原有协议。此分类不是完整复制前清理验收。

真实回归额外覆盖两类不在祖先范围内的清理：复制前独立语句的临时对象析构、
复制前已经结束的嵌套作用域中的自动对象析构。二者可增加全局计数，同时祖先
检查仍checked；报告中的其他作用域清理和源对象保持仍未建立。该样例没有修改
源值，不是源值错误放行的反例。包围复制点的作用域正常退出清理与先前已经结束
的清理必须分别处理；当前尚无完整复制前清理清单或自动局部对象析构效果证明。

`object_use_closure.copy_cleanup_observations` 是另一个独立状态的子报告，
schema为`copy-enclosing-cleanup-observations/v1`。它沿所选copy的唯一语义祖先链
收集所有`ExprWithCleanups`，检查重复AST节点一致，并要求同次native metadata
逐个精确匹配wrapper/subexpression，`num_objects`为整数0、
`cleanups_have_side_effects`为布尔false，且不与AST的可选flag冲突。
缺失、重复、错绑、未知协议或副作用flag均unknown；相同wrapper跨多个copy只
记一次观测，不当作执行次数。无此类祖先时只报告路径上没有wrapper，无需metadata。

插件的非穷尽coverage未被升级；此子报告不枚举其他作用域析构、callee内清理或
全部动态析构事件，不根据`num_objects==0`推断“没有析构”。native false flag
仍是可信Clang观测，不是独立效果证明。子报告绑定root与cleanup metadata哈希，
不消费生成器提供的成功结论。父显式闭合checked不蕴含它checked；它checked也
不解除alive、source历史保持或部署义务。

## 复制目标对象与record析构

`inspect_effects` 与条件值入口另返回 `object_boundary`（`copy-object-boundary/v1`）。
它在fresh结构与局部效果成功后，要求complete/prvalue复制直接初始化普通自动
VarDecl（单独DeclStmt、CompoundStmt内、无属性/storageClass/TLS），或匹配下述
精确按值参数。源和目标声明ID须不同；placement-new、引用目标、子对象、static、
TLS、未支持wrapper保持unknown。不把声明ID不同单独当作对象分离证明。

同时要求同一完整record的Clang `definitionData.dtor.trivial` 为布尔true，
无nonTrivial/userDeclared冲突；存在析构声明时还须唯一、implicit/defaulted、
无未支持属性或非空body。缺少正面trivial证据不能用“没看到析构函数”替代。
显式用户`=default`析构目前也保守unknown，不代表其语义一定有副作用。

成功只给出“若该复制在有效C++程序中求值，目标与求值所得源实参是不同完整
对象”及该record的trivial析构边界；不是原始捕获变量身份、物理ABI地址非重叠、
生命周期或历史值保持证明。完整表达式的其他cleanup、其他实参和callee效果
仍未建立，尚未接入native cleanup祖先链。父结构checked不蕴含此子报告checked。
参考[C++对象模型](https://eel.is/c++draft/intro.object)、
[析构规则](https://eel.is/c++draft/class.dtor)及
[传参临时对象](https://eel.is/c++draft/class.temporary)；编译器可为传参引入额外临时对象，
所以本报告不声称唯一物理存储或固定析构执行时序。

## 复制实参与按值形参的精确绑定

同一 `record_copy_check.check` 还返回独立 `parameter_target` 子报告。先fresh
完成复制结构和局部效果检查，再从完整AST查找copy表达式的直接父CallExpr；
不需要调用者填写预期的callee或参数ID。相同ID的重复copy/call必须一致，所有
副本必须对应同一个call ID和实参位置；不把重复dump当成执行次数。

只接受complete/prvalue复制、直接FunctionToPointerDecay→DeclRefExpr→唯一
普通FunctionDecl、精确签名和按位置对应的同一record alias按值形参。模板、
重声明、variadic、间接调用、引用形参、额外wrapper、参数属性/默认值或冲突
副本均不建立此绑定。名字不赋予语义；callee可以只有声明而无body。

`copy-parameter-target-binding/v1` 的checked只说明“完整prvalue复制实参对应
精确按值形参”。没有绑定C++方言、copy-elision与物理ABI，故不宣称实参临时量
就是最终参数对象；源/目标动态非重叠、其他实参顺序及效果、参数析构、callee
body、配置API和launch语义仍未知。原v1主status仍仅描述字段值关系，不能因
`parameter_target` checked自动解除source历史保持义务。

## 源声明与复制的结构顺序

`object_use_closure.check` 完成fresh引用闭合与立即调用检查后，单独返回
`source_order`。它在同一函数的语义AST视图中记录实际祖先路径，跳过重复closure
record body，使用source所在CompoundStmt的直接child对象顺序（非行号/offset）
检查声明在复制所在语句之前。每层lambda必须沿该copy真实祖先路径，对应本次
fresh检查得到的立即调用ID，且copy位于lambda body而非捕获初始化器内。

支持完整处于source同一作用域后续语句中的switch，其Case/Default必须归属该
支持的switch；不推导选择了哪一分支。source之前或作用域之外的switch不支持。
同样支持完整位于source作用域后续child的 `do { ... } while(false/0)` 宏包装，
body须为CompoundStmt，条件只接受childless bool false，或精确的
IntegralToBoolean←childless int字面量0；不做任意常量折叠、不按宏名放行。
Break绑定最近的受支持switch/do且不跨lambda，Case/Default不得越过do跳入体内。
其他循环、continue、goto、label、try/coroutine、GNU statement-expression及未识别Stmt保持
unknown。原先闭合扫描拒绝的空AST placeholder仍然拒绝，不为顺序子报告放宽。

`source-copy-structural-order/v1` 的checked仅是结构顺序和立即调用路径证据。
执行可达性/次数、source动态lifetime、非局部外部控制效果及历史值保持仍未知；
原有capture协议中的活跃对象和same-activation假设不会自动删除。
主引用闭合可以checked而source_order未知，调用者必须检查所需的子报告范围。

## 显式源引用的复制效果组合

`object_use_closure.source_reference_use_effects` 只消费本次fresh执行的
`record_copy_check.local_copy_effects`，包括direct copy及capture-source报告内部
的copy检查。每条记录须匹配同一root hash、源声明ID、copy ID及其捕获路径类别；
复制集合必须完整且不重复。任何copy效果未知，整个效果子报告保持unknown。
by-reference capture只按已检查的原生边及立即调用路径分类，不建立动态非逃逸。

该子报告描述copy中按AST角色区分的源字段读取、目标字段初始化及额外地址发布
分类；不证明source/destination动态不重叠、隐式生命周期效果或历史值保持。
普通局部copy无需绑定按值形参才能进入此效果分类；`parameter_target`是独立义务。
主v1状态仍只表示显式引用闭合，不因新增效果未知而改写。未来历史组合必须分别
要求效果和顺序子报告checked，并另行处理尚未解除的动态义务。

## 以源码调用链替代 closure 来源假设

`capture_source_check.check` 新增 `capture-source-assumptions/v2` 输入协议，
输出 `capture-source-check/v2`。与v1唯一的协议键差异是移除
`closure_instances_from_recorded_lambdas_assumed`；v2若仍携带此键则unknown。
root/copy/source绑定、ABI，以及alive、same-activation、source-valid前提仍必需。
v1保持原条件身份结论，不自动迁移或冒充源码证明。

v2对原生reference capture链的每层lambda重新执行立即调用检查，核对closure
声明和root hash，并在该copy唯一语义祖先路径上确认call→lambda→body关系。
不遍历closure record中的重复body作为额外执行，不把捕获初始化器当成新lambda
的body；具名、传出、返回或嵌套外层非立即调用的closure不在支持范围。
成功时identity_completion不再列出origin布尔，来源由closure_origin子报告承载。
该结论以copy被求值为条件；不证明该copy可达、执行次数、对象仍活着或值保持。
现有object_use_closure可直接消费v2协议，不接受外部成功子报告替代fresh检查。

`capture-source-assumptions/v3`进一步移除same-activation布尔，输出check/v3；
v1/v2均保留原键集与保证。v3只接受唯一普通FunctionDecl直接CompoundStmt中的
自动块局部source，要求source声明与copy都位于同一精确函数body对象之下，
reference capture链与语义lambda路径一致，再fresh核验全部立即receiver链。
coroutine/function-try-body、具名或传出的receiver等不支持，返回unknown。
协议仍必须提供source_initialized_alive_assumed及source_program_valid_assumed。

这里的activation限定为包围函数的本次求值，不是线程号或词法声明ID。设计依据
是自动块变量的存储期规则及嵌套引用捕获原实体的规则（[basic.stc.auto](https://eel.is/c++draft/basic.stc.auto)、
[expr.prim.lambda.capture](https://eel.is/c++draft/expr.prim.lambda.capture)）；将其连接
到当前receiver链是本工具的受限语义推导，不是标准对本实现的正确性证明。
递归调用返回后，原始立即closure仍引用当前外层调用的source，递归本身不拒绝；
存储旧closure后在另一调用中使用则不满足原始receiver形状。生命周期、初始化
完成及值保持仍不能由同次调用关系推出。CPU递归回归只是有限执行验证。
