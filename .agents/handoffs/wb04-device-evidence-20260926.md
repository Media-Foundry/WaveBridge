# 同次设备整数证据编排交接

- 日期、分支、基线：2026-09-26，wb03-source-ast，0c5e123。中文回复，直接commit/push，不开PR。
- 代码：device_evidence.collect以完整root和device-integer-protocol/v1为输入，fresh launch_binding → row_offset（内部fresh row/thread/column）→本次thread报告→shared_storage。检查同root/kernel/launch/ABI/协议哈希，不接受外部成功报告。顶层成功状态仅evidence、all_selected_integer_checks_passed=true，保持source_program_checked/deployable=false。
- 实现边界：只是条件证据编排，不是新算法或整核验收；剩余配置历史、指针/alias、参与/收敛、shared值/同步、归约值/FP、目标改写与设备执行义务均保留。max_ast_nodes仅控制launch子checker，其他子checker用各自原预算。
- 测试：7项mock子checker编排单测明确标注，不冒充源码结果；2项真实Clang无mock链验证静态launch成功不足以补缺设备协议、错槽位先停。匹配AOCC17 native插件启用后735项CPU通过（57.812秒）、252项Clang专项通过（54.696秒），demo退出0。日志artifacts/wb-device-evidence-y8sNOQ/tests.log、clang.log、demo.log。
- Sol只读复核：没有发现阻断性问题；并从固定完整HIP AST/source记录核对了当前axis字段和external coordinate leaf声明。未读取oracle、未运行GPU。
- 当前生产任务：PYTHONPATH=src python3 artifacts/wb-device-evidence-y8sNOQ/llama.py，会话78893仍运行，日志llama.log。复用同一会话到终态，不能因观察超时重启。src保持冻结，运行前后记录79个Python哈希。脚本输出protocol.json与最终llama.json，尚无结果就不得称通过。
- 固定输入：artifacts/wb03-full-input-EUYEix/source/ast.json，字节SHA256 f0114e85794b328b2d9be4796b0fdbd6dee270164c87548b0d7beeaedadd1f25；root SHA256 67b7d6f3c99092526d636fd87c7926670dc0bdc52a779687a666ef9386955aa2。kernel 0x2ebf3760、launch 0x2ec2f4e8、config 0x2e295a90；完整人工standalone HIP TU，不是原始上游TU。
- 外部协议：ABI来自examples/abi/row-offset-conditional.json；axis ctor 0x2e20afe0，fields x=0x2e20ac18/y=0x2e20ac80/z=0x2e20ace8；local leaf 0x2eabf708、group leaf 0x2eac0120，声明size_t(unsigned int)，外部返回类型协议unsigned long、axis0。坐标与API轴含义显式提供，不从名字推语义，不提供历史保持结论。host guard assumptions显式true，报告保留其原条件性质。
- 实现SHA256：08543b7b886ee252592700a83cb8137ab17b805e6ad4d7737dcd19a2bcf1e80b；单测SHA256 75974617b868c06eb7779c637d0df817c91007ed93e644c5159dd087cae08abb；真实Clang测试SHA256 3816e887c6c366a69f1ebbeb03e847e114ef26e3f125db17c2b1de85ec9e3198。
- 没有执行：GPU编译/运行、性能计时、候选生成、浮点关系检查。
- 下一步：取得78893终态及完整失败/成功范围，核对79个实现哈希后解除冻结；将同次fresh chain/条件routes/output恢复与上述整数证据精确绑定。不能因整数支路通过就签整核或放行部署。
- 提交：本实现、测试、文档和交接直接commit/push当前分支；artifacts仅本地忽略，不合并master。
- 阻塞：无；在运行的静态重放不是阻塞。

## 生产终态

- 会话78893已退出0，134.91363753000041秒。顶层evidence，all_selected_integer_checks_passed=true；launch_binding、row_offsets、shared_storage均checked。不是整核checked，九项剩余义务原样保留。
- llama.json SHA256：11f9840b52d4546c82f9258a43b0978ed2bca7999e652d530fe33d04252f9997。
- implementation_hashes_stable=true，79项记录与当前源码sha256sum --check --status复核退出0。源码冻结解除；本轮所有检查会话终结，不需继续轮询。
- 下一步推进同次fresh chain/条件routes/output绑定及其负例，而非重复运行已完成整数支路或宣称GPU适配闭环完成。
