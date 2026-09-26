# 精确选点与全TU发现分离交接

- 日期、分支、基线：2026-09-26，wb03-source-ast，8c80e3e。中文回复，直接commit/push，不创建PR。
- 实现：verification/launch_binding.py保留全TU discovery报告，但不同非空ID的未解析launch不阻止精确选点。same-ID内容冲突仍全局unknown，任意launch缺ID拒绝，选定未解析位置无唯一supported site则unknown。没有修改launch_facts的原发现语义，也没有改变配置值/对象保持/部署边界。
- 回归：真实selected_launch.cu包含两个精确launch及一个未实例化模板launch；5项新增Clang测试覆盖两精确选点、未解析选点、串用槽位、同ID冲突和缺ID。证据篡改测试不是GPU错误实验。Sol只读复核未发现狭窄结论的阻断问题。
- 验证：匹配AOCC17 native插件启用，make check 726项通过（58.994秒）；Clang专项250项通过（55.170秒），make demo退出0。日志在artifacts/wb-selected-launch-VBYCGB/。c69ecce CI 36241445114与8c80e3e CI 36241526362均completed/success；本次新提交CI尚未核验。
- 完整vLLM：production.py会话26736退出0，154.9196237629949秒；输入完整AST字节SHA256 fc00b07d7c0da2725949db3daa98cc744751874f8e6c5f3f79106c7022877559。kernel 0x44cbe168、launch 0x44cbe3d8、configuration 0x2ec97d40，四配置槽及六参数位置静态checked。CUB未解析位置原样保留，complete_launch_resolution=not_established。报告production.json SHA256 0156f0e9c89bd34d5516fb3efcad97818a3f48fd7edf5dac36593d3bbbe999a9。
- llama首例：llama.py会话26920退出0，21.848360228003003秒；输入artifacts/wb03-full-input-EUYEix/source/ast.json字节SHA256 f0114e85794b328b2d9be4796b0fdbd6dee270164c87548b0d7beeaedadd1f25。kernel 0x2ebf3760、launch 0x2ec2f4e8、四槽及四参数位置静态checked。报告llama.json SHA256 7a49a2007a25c8d00d2031af55a7b86b9331e8ac481ea412fe5ef6a12e659037。它是人工提取HIP standalone，不是原始生产TU自动转换。
- 两次都从完整AST fresh检查，未消费旧成功报告；78个Python实现哈希前后一致，结束后sha256sum --check --status逐项复核退出0，源码冻结解除。
- 实现SHA256 bcce18e5d8944c458806e23f0d02e8a8f63b25473d3aed94f4c0d31f7f805a58；新增测试SHA256 96f858eb899f6cd69efa1bd357ebf41d7b5ac0a67bb083c3e0de9cbd7564d038；fixture SHA256 de9bf6dc81367e0aa6357b40d54c792970505c479e37e6eac1384bb68f170602。
- 没有执行：重新编译生产TU、GPU运行、候选生成或性能计时。此前生产前缀cleanup unknown保持不变。
- 保证：只签静态配对，不签配置API语义、参数值、源对象历史、可达性、浮点正确性或部署。所有原有未解除义务保留。
- 下一步：以已固定llama完整standalone AST为首例，构造同root/ID/launch协议的原子设备证据路径：launch_binding → row_offset_check → 使用其fresh thread子报告调用shared_storage_check，再连接fresh chain/条件routes/输出恢复。协议只提供ABI/API/输入域，不能提供待证明的保持/等价结论。此前交接wb04-launch-binding-20260926.md有具体调用边界。
- 未提交/未推送：提交上述实现、fixture、测试、文档和本交接后push当前分支；artifacts本地忽略不上传，不合并master。
- 阻塞：无；本轮所有运行会话已终结，不需重启或继续轮询。
