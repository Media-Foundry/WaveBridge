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
