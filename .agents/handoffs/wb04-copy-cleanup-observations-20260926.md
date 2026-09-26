# 复制祖先cleanup原生观测

- 2026-09-26，wb03-source-ast，基线1991128。中文回复、直接commit/push，不开PR。
- 修改object_use_closure.py：新增copy_cleanup_observations子报告，独立状态；不添加外部假设布尔。
- 同一完整AST中，逐copy取得唯一语义祖先路径，收集ExprWithCleanups。semantic ID须唯一，完整index中的同ID副本须一致。
- 有wrapper时要求同次native观测：coverage/count semantics固定、全局metadata ID唯一非空、wrapper/subexpression精确匹配、count严格int 0、side-effect严格bool False，与可选JSON flag一致。
- 无wrapper仅报告选定路径无该节点，无需metadata。不将非穷尽plugin观测升级为全函数cleanup完整性，不将num_objects=0解释为无析构。
- child记录root与cleanup metadata哈希；source lifetime/历史保持、其它scope析构、callee/其它实参效果保持未建立，alive协议不删。
- compiler/verification/README.md及docs/architecture.md同步保证边界。Sol负责真实native组合测试与只读复核，无阻断发现。

## 本地验收

启用WB_NATIVE_CAPTURE_PLUGIN=$PWD/artifacts/capture-plugin-cleanups-gYQ3gz/libwavebridge_capture_plugin.so，
WB_NATIVE_CAPTURE_COMPILER=/opt/AMD/aocc-compiler-5.1.0/bin/clang++。

- make check：681项，退出0。
- PYTHONPATH=src python3 -m unittest discover -s tests -p '*clang*.py'：205项，退出0。
- make demo：退出0；git diff --check通过。
- 日志：artifacts/wb-copy-cleanup-composition-LapMjC/{tests,clang,demo}.log。
- 正例为无wrapper及真实false/count0祖先wrapper。真实负例将SideEffectTemporary和copy放在同一comma full-expression，native flag=true/count0，父closure checked但cleanup unknown。
- 合成边界：缺记录、重复、错绑subexpression、flag true/nonbool、count nonzero/nonbool、JSON flag true/null、coverage缺失及count semantics错误。未称这些合成元数据为真实运行。

## 生产重放待完成

脚本已准备：artifacts/wb-copy-cleanup-composition-LapMjC/check.py。
命令：PYTHONPATH=src WAVEBRIDGE_JSON_HASH_MODE=one-shot python3 artifacts/wb-copy-cleanup-composition-LapMjC/check.py。
固定完整AST输入，旧工件只提供外部ABI/domain/v3迁移协议；不复用旧checked子报告。
计划验收整个object_use_closure/v3及新增cleanup子状态，77个实现文件哈希前后核对。
本交接只确认本地验收，尚无本轮生产组合终态，无GPU运行。
实现提交后启动并冻结源码；句柄记录在同目录NEXT.md，禁止因观察超时重启。
下一步先核查生产重放，再考虑显式组合结构/对象/cleanup/来源/顺序；仍不能直接解除alive或宣称历史保持。

## 生产重放终态（替代上节待完成状态）

- 实现基线0e441b424f711f50b7ca0cd353b735bfbe8ee2b6；会话21522退出0，耗时666.7020661530114秒。
- 工件artifacts/wb-copy-cleanup-composition-LapMjC/report.json；SHA256为3e8085ba0c4814539f6e4d2bec3adba1999ff0feab81bccaaa4958052ed825ff。
- 固定完整AST文件SHA256为f80432e744686fdc1390308073a3cd7e1b1d1ba5afd065198dcc292ab21ee9ee；root hash为ce0f70bbec8ae7dfc727882d5185a1e13982c9facc32c52346e4f5878413f7ba。
- 主status、source_order、source_reference_use_effects及新增copy_cleanup_observations均checked；不是只查看父status。
- copy 0x37382628/0x37388288/0x3738de68各绑定两个祖先wrapper；共享0x373938a8，另分别为0x37384790/0x3738a370/0x3738ff50。四个不同wrapper均native count=0、side-effect=false；不将其解读为零析构事件。
- 77个实现哈希前后一致；终态后用jq提取implementation_hashes并交给sha256sum --check --status，退出0。源码冻结解除。
- 三个capture v3协议仍保留source_initialized_alive_assumed和source_program_valid_assumed；source lifetime、历史值保持、其它scope cleanup及callee效果未建立。没有GPU执行。
- 0e441b4远端CI 36234845414 completed/success；本次只补生产证据，未增加测试数量。
- 下一项：拆分capture语法恢复与带alive/readable假设的值检查依赖；保持v1/v2/v3兼容，不以条件checked反向证明alive。
