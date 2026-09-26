# 归约计数与输出结构连接交接

- 日期、分支、基线：2026-09-26，wb03-source-ast，826d679。中文回复，直接commit/push，不开PR。
- 实现：新增device_evidence.collect_rmsnorm，不改变原collect/v1输出。只消费本次collect的整数证据；thread/shared链须完整一致，精确绑定helper调用、accumulator、shared array、source/output/count与两个已检查列循环，再fresh恢复output并独立运行xor_routes/block_routes。
- 显式模型参数：width/block/offset来自同次链，first/final reduce为同声明；writer来自helper与checked索引；load_offset=0来自gather=lane；shared_slots来自checked available_bytes / 外部float大小且要求整除/required bytes一致。barrier=True明确是尚未证明的全员到达与写入可见性模型前提，不是barrier调用语法的推论。
- 输出：rmsnorm-structural-evidence/v1，全部连接成功仅evidence；output仍recovered，routes仅条件贡献计数checked；整数包九项剩余义务完整保留，source_program_checked/deployable=false。
- 验证：匹配AOCC17 native插件启用，743项CPU通过（59.275秒）、253项Clang专项通过（55.081秒）、demo退出0。新增7项测试mock源码/整数恢复但运行真实路由checker；错误阶段列表被rejected，错绑定unknown。1项真实Clang无mock链确认integer unknown不能被新入口升级。Sol只读复核未发现阻断问题。826d679 CI 36242463001 completed/success。
- 日志及脚本：artifacts/wb-rmsnorm-evidence-vsAsE8/，tests.log/clang.log/demo.log。
- 完整首例重放：PYTHONPATH=src python3 artifacts/wb-rmsnorm-evidence-vsAsE8/llama.py，会话18571仍运行，src冻结。输入固定完整standalone HIP AST字节SHA256 f0114e85794b328b2d9be4796b0fdbd6dee270164c87548b0d7beeaedadd1f25；外部协议复用wb-device-evidence-y8sNOQ/protocol.json，SHA256 79f7871193fe0825586e9b24f544910cf2c34a17f4100fc4a323bc596311fa04。未读取旧成功报告作为检查输入。
- 实现SHA256 0583d75a24152ae7f9a79bed3c724dbae57864e3a8e06c359c381a569973fd63；组合测试75b507d1899482a7a216e214d3c6d3dd9dcc45d8a6609ec5f8c9a408da712874；真实Clang测试6eef1a582b9de47189fac0b5566bcebd9517c7a2cb88937a1e3810c0f7ba1ebc。
- 没有执行：GPU编译/运行、性能评测、真实候选生成或浮点等价检查。首例仍人工提取standalone，非原始完整上游TU自动支持。
- 下一步：取得18571终态、核对79个实现哈希；比较本次result.checks.integers与上一轮wb-device-evidence-y8sNOQ/llama.json的result完整JSON是否一致。随后进入绑定源码/launch的未验收候选工件，独立重提取目标；不能因条件计数通过解除同步/FP或硬件前提。W7900仅普通wave32已验证，native64不得部署。
- 提交：本实现、测试、文档与交接直接commit/push当前分支，artifacts仅本地不上传，不合并master。
- 阻塞：无；使用原会话继续观察，不能因超时重启。

## 重放终态

- 会话18571已退出0，136.15414187000715秒。integers=evidence、output_structure=recovered、xor_routes/block_routes=checked，顶层evidence且all_selected_relations_connected=true。不是整核/FP/部署通过。
- llama.json SHA256 c70757263438e10f81e0c768a3aa723d32d3296a40b4ed1121cd6e265a3d4e5b。79个实现哈希前后一致，结束后sha256sum逐项复核退出0。源码冻结解除。
- cmp --silent比较jq -cS规范化后的上一轮result与本轮result.checks.integers返回0，原整数完整JSON一致。无测试会话仍运行。

## 下一轮真实候选范围（Sol只读建议，尚未实现）

从同次fresh xor/helper的width_declaration_id交集选声明，不按kLogicalWidth名字
特判；首例为0x2ebf1c10。要求唯一普通const int constexpr VarDecl，其唯一非Attr
initializer为childless prvalue IntegerLiteral 32（本例0x2ebf1c78，源offset486，
tokLen2），位于哈希绑定的主源码而非宏/头文件。扫描精确DeclRef使用，分类为
已恢复xor的width/2与shuffle width、block group/lane/group-count及独立只读诊断；
写入/取址/引用别名/未分类使用拒绝。仅修改该literal token为64。

block声明0x2ebf1d50应保持256；launch的32*sizeof(float)保持128 bytes，不随
协作宽度替换。函数名中的logical32、数据域、epsilon和FP协议不得全局修改。
新源码必须完整保存kernel与launch，fresh目标AST重选ID并重新检查，绝不能沿用
旧pointer IDs/checked报告；预期width64、offsets[32,16,8,4,2,1]、groups4、
writer0、可用shared32槽。这里只是未验收candidate；W7900无已验证wave64路径，
source-to-intrinsic/同步/参与/FP等义务仍在，deployable必须false，不运行GPU。
