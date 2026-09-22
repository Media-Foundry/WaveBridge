# 编译器关系检查

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
