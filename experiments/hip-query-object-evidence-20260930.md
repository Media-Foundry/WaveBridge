# 查询地址实参与字段快照对象的对应

基线 `2c588d8`，分支 `wb03-source-ast`。本轮没有 GPU 执行。

上一轮已连接 query 返回值与正常返回守卫，但没有证明 query 的参数与
后续读取的 properties 对象有什么关系。本轮在既有 `field_snapshot` 模块
增加 `check_query_object`，只消费原始 AST 和函数选择，不接受旧成功报告。

先 fresh 检查字段快照后缀，再选择紧邻该后缀的最后一条前缀语句，fresh
检查它的 query/guard 调用。检查器在 query 实参中寻找唯一的 builtin
`&object`，要求直接 DeclRefExpr 的声明身份和类型与字段快照基对象一致。
实参位置从 AST 推出，不假设输出对象总在第零个位置；零个或多个候选均未知。
指针别名、算术、显式转换或其它不支持形态不被替换成“等价地址”。

**checked 只说明同一声明的地址/字段基对象对应，以及语句在函数体中紧邻。**
它没有证明 query 将该指针当成输出，也不证明字段已写入、初始化或具有特定
数值。报告保留 `query_argument_direction=unverified`、
`query_output_effects_verified=false`、`field_numeric_domain=null`。
动态对象生命周期仍是来自子报告的显式前提，不以声明 ID 相同替代生命周期证明。
完整函数可达性、query 成功与实际正常返回也仍未建立。

driver 保存 `query_snapshot_object_check`，兼容的 `field_snapshot_check`
来自本次组合内 fresh 子检查，而非重新相信旧报告。两份子检查的 root hash
必须相同；选择、输入 root 和身份策略均有哈希。
消费者必须检查组合父级 status；父级 unknown 时，即使 snapshot_check 单独
checked，也不能声称 query-object 对应成立。Sol 只读复核未发现阻断项。

## 命令与回归

```bash
PYTHONPATH=src:. python -m experiments.softmax_launch_native \
  --profile hip --native artifacts/wb-hip-native-20260927-01/native.json \
  --output artifacts/wb-hip-query-object-20260930-01/report.json \
  --host-dimensions
PYTHONPATH=src python -m unittest discover -s tests -p test_field_snapshot_clang.py -v
```

固定输入 SHA256：
`46ac52b1c672fadd0e5a66bb3ab380373e0cd69929713d96e7010f375a0cd63e`。
6 项真实 Clang 定向测试通过，覆盖地址一致和位置换位、不同对象、非邻接、
指针别名、两个候选地址、丢弃 query 结果、身份冲突、预算及输入不修改。
完整回归和真实重放结果在验收补记中记录。

下一步应在已绑定声明/参数/对象/字段上冻结 API 输出协议，并区分协议假设与
本次源码建立的关系；不得把“传入地址相同”改写成“API 已成功写入 width=32”。

## 验收补记

完整 `make check`：1321 项，100.449 秒，无跳过；日志
`/tmp/wb-query-object-check.log`。同前轮环境：visibility/unary builtin/using-shadow
使用 SDK Clang 23 与匹配插件，旧 native capture 使用 AOCC Clang 17 与匹配
插件，普通 fixture 使用 PATH clang++。`make demo`、`git diff --check` 通过。

真实 HIP 重放完成，inputs_unchanged=true，组合父级 status=checked。
报告 SHA256：
`fcaea1377a313219fa2764ef62b57ec0207cb22b753675f421cc12f4c4ff1074`。
查询调用 `0x220432d8` / 声明 `0x217b69b8` 的第零个实参 `0x220431a8`
对应形参 `0x217b6810`，其直接取地址对象是 `0x22041e90`；同一对象的字段
`0x21318820` 在 `0x220439f8` 读取，随后赋值 `0x22043a10`。
包装调用 `0x22043958` 与快照赋值紧邻。
query_argument_direction 仍 unverified，field_numeric_domain 仍 null，
API_success_verified 仍 false；没有新增设备运行或数值保证。
