# kernel/launch 静态绑定交接

- 日期、分支、基线：2026-09-26，wb03-source-ast，facc5ef。中文回复，直接commit/push，不开PR。
- 已完成：新增verification/launch_binding.py和8项真实Clang测试；更新架构、检查器说明与状态。fresh AST恢复不接受旧成功报告；根哈希、kernel/launch/configuration精确ID、四个配置槽位、kernel参数位置均绑定。
- 只读审查：GPT-5.6 Sol未发现窄静态结论的阻断放行问题；补充配置声明相同副本计数。未来可进一步统一内部异常边界，不扩展当前语义保证。
- 实际验收：启用WB_NATIVE_CAPTURE_PLUGIN=artifacts/wb-local-record-native-i9nCNe/libwavebridge_capture_plugin-final.so及匹配AOCC17编译器；make check最终721项通过（57.801秒），Clang专项245项通过（54.127秒），make demo退出0。日志分别tests-final.log、clang-final.log、demo.log，目录artifacts/wb-launch-binding-urZCXK。
- 最终源码SHA256：af450c78904e3e1d6c7a51fe1cbd9e74146b4d9728cf28398e4a23f241bfe79d；测试SHA256：c4da0c99ff46ef29f9152632ddd8538f6f44be0cc6bf7ba3d9eead45220ffa16。
- 生产重放：PYTHONPATH=src python3 artifacts/wb-launch-binding-urZCXK/production.py，输出production.log。工具会话34115仍运行，已轮询确认非终态；不要因观察超时重启。src保持冻结，脚本记录78个Python实现前后哈希。
- 固定输入：artifacts/wb-production-local-scopes-BuluwQ/ast.json，字节SHA256 fc00b07d7c0da2725949db3daa98cc744751874f8e6c5f3f79106c7022877559。完整root输入，不用diagnostic切片；Float kernel 0x44cbe168、launch 0x44cbe3d8、configuration 0x2ec97d40。四槽0x44cbceb0/0x44cbcf08/0x44cbcf40/0x44cbcf80；槽1恰为前面对象复制研究的Float copy ID，但本次不据此推导历史值。
- 没有执行：生产重新编译、GPU作业、候选生成、性能对比。未把AST篡改负例称为真实设备错误。
- 保证范围：位置0–3只是语法槽，不自动等同于API语义；配置值、对象保持、host可达性、API含义、整核与部署均未建立。此前production prefix unknown保持不变。
- 下一步：轮询34115到终态，复核production.json、实现哈希、报告具体范围，记录成功或unknown并解除冻结；再在同AST/协议下原子组合现有设备局部门控。不要将各局部checked升级为整核保证。
- 提交与远端：提交本实现/测试/文档并push当前分支；本地artifacts忽略不上传。最终提交ID由git记录，不合并master。
- 阻塞：无；完整生产重放进行中不是阻塞。

## 下一步可复用链（Sol只读核查）

首例llama手工baseline可按launch_binding → row_offset_check → 复用其fresh
checks.thread调用shared_storage_check → fresh reduction_chain → 条件xor_routes/
block_routes → fresh normalization_output组织。row_offset内部已fresh调用row、
thread、column，不必重复跑另一套。thread_report必须来自本次调用内存结果，
不能把任意存盘checked视为真实checker输出。路由checker只有标量模型输入，
须与fresh chain的width/block/offset/writer/shared/barrier逐项绑定。
当前没有统一消费平方贡献、shared读写值、收敛/同步和浮点后缀的整核checker；
下一交付应如实称同root/ID/launch的条件证据包，不借原子编排签发整核通过。
