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
