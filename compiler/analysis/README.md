# 关系恢复

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
