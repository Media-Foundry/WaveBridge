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
