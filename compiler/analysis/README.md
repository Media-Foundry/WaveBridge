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
