# Clang23 原生采集交接

- 日期、分支和基线：2026-09-27，wb03-source-ast，1619f08。
- 目标：解除实际HIP工具链缺少匹配插件的障碍，中文回复，直接commit/push。
- 实际进展：固定源码8f497e0稀疏检出；SDK自带TableGen生成170项开发头；原插件C++不修改即可编译。显式depfile target重放编译后711项依赖observed，so与首次构建逐hash相同。
- 工件：artifacts/toolchains/clang23-native-8f497e0/；实际HIP采集artifacts/wb-hip-native-20260927-01/native.json，SHA46ac52b1c672fadd0e5a66bb3ab380373e0cd69929713d96e7010f375a0cd63e。版本与命令在experiments/clang23-native-build-20260927.md，紧凑哈希索引在同名前缀result JSON。
- 验证：Clang23下24项原生采集回归通过（0.432秒）；实际HIP native collected，334项依赖，pilot三份派生源码一致；精确nan builtin在默认100万节点预算下结构checked。demo/diff通过。
- 重要更正：本次native builtin引用为prvalue，现有checker无需放宽。此前JSON的lvalue现象不能归纳为版本规则，成因未验证；两份工件都保留。
- 未执行：本轮GPU、完整CPU套件在Clang23上的回归、效果/值/整核等价验证。依赖观察不等于冻结完整构建闭包。
- 失败/中止保留：两份低效整仓压缩包下载明确中止、未用于构建；首次CMake缺libc公共头；首次depfile target不符合观察器协议。它们均不计为成功。
- 当前无活动下载/构建/采集进程；所有本轮会话已终止或成功结束。
- 下一步：在新native中绑定quiet_NaN方法0x203335e0到builtin call0x20334a68/callee0x203347a8，使用明确外部leaf效果协议连接现有guarded-work检查；不要复用旧ASTContext ID或把lowering探针当完整源码证明。
- 提交安排：提交证据、结果索引、状态与本交接；原始大工件不入Git。不创建PR、不合并master。
