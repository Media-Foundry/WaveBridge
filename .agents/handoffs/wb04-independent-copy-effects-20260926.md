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
