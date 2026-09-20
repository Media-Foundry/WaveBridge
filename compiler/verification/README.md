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
