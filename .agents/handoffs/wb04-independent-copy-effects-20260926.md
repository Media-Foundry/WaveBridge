# 独立复制结构效果

- 日期：2026-09-26；分支wb03-source-ast；基线d103430。始终中文，无PR，验收后直接提交推送当前分支。
- record_copy_check新增inspect_effects，独立于条件值入口；两个入口共享私有结构解析器，不重复构造器规则。结构映射不再携带值相等语义。
- 条件值接口保持原有属性宽容边界；结构效果未知时不随值checked升级。结构检查不需要alive/readable/normal-return，值接口仍明确保留这些前提。
- tests新增真实Clang正例、禁用旧check的依赖回归、错误字段映射、预算和输入不变性、真实属性边界。标准<new>反例经CPU执行确认两次复制读3和99，总和102；效果unknown。
- GPT-5.6 Sol子代理负责测试，主代理负责实现、文档与完整验收；不把mock依赖检查称为源码语义证明。

## 实际验证

主代理启用匹配插件及Clang17：
WB_NATIVE_CAPTURE_PLUGIN=$PWD/artifacts/capture-plugin-cleanups-gYQ3gz/libwavebridge_capture_plugin.so
WB_NATIVE_CAPTURE_COMPILER=/opt/AMD/aocc-compiler-5.1.0/bin/clang++

- make check：673项，退出0，日志/tmp/wb-copy-structure-check.log。
- PYTHONPATH=src python3 -m unittest discover -s tests -p '*clang*.py'：197项，退出0，日志/tmp/wb-copy-structure-clang.log。
- make demo：退出0，日志/tmp/wb-copy-structure-demo.log。
- 子代理系统Clang与ROCm Clang23专项各23项通过。
- git diff --check通过。

未重放5GB完整生产TU，未运行GPU；此前d103430对应TU证据不冒充本轮结果。
本轮仍不建立源目标动态非重叠、source lifetime或历史值保持，不删除capture的alive协议键。
ADR 0003与检查器说明、docs/status.md已同步。工作区变更均属于本轮，待此交接写入后提交推送。

下一项：在冻结源码后重放固定生产TU，核对独立结构入口与既有组合检查；再设计显式消费结构效果的生命周期组合，不引入noalias/value-preserved同义假设。

## 后续完整TU终态（同日）

- 实现固定454f5749d765eb7d887dc34da9876d906da47ff1；其CI 36233180736 completed/success。
- 目录artifacts/wb-independent-effects-r0Eik8；check.py与run.log、三个复制点JSON、report.json均保存。
- 命令：PYTHONPATH=src WAVEBRIDGE_JSON_HASH_MODE=one-shot python3 artifacts/wb-independent-effects-r0Eik8/check.py。
- 执行会话95200／宿主PID254894已退出0，未重启；耗时773.8515560439992秒。
- 输入AST文件SHA256 f80432e744686fdc1390308073a3cd7e1b1d1ba5afd065198dcc292ab21ee9ee；只从旧工件读取外部ABI、domain、capture协议，不复用旧子报告。
- 三个独立结构点0x37382628、0x37388288、0x3738de68均checked；root均ce0f70bbec8ae7dfc727882d5185a1e13982c9facc32c52346e4f5878413f7ba，源均0x373701f0，按值目标形参均0x2135ca90、位置1。
- fresh object_use_closure主状态、source_order、source_reference_use_effects均checked；三个capture-source-check/v3仍保留source_initialized_alive_assumed及source_program_valid_assumed。
- 独立结构仅记录direct_same_field_read_initializer，不带值关系/live/readable/normal-return前提；仍信任完整AST和整数ABI。
- 报告SHA256：2435d06e172c423c691b7675f8a3a2ab6de51b873a4dec646539dbc0d58290f4。
- 77个实现哈希运行前后一致；从report.json提取implementation_hashes经sha256sum --check --status复核当前源码，退出0。源码冻结已解除。
- 未运行GPU，不推出lifetime/历史保持/部署能力。下一步是受限对象分离与trivial析构/cleanup门控；析构反例见wb04-copy-cleanup-audit-20260926.md。
