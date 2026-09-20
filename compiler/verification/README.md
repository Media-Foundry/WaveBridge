# 编译器关系检查

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
