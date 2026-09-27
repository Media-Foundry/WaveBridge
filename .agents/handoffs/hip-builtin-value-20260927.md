# HIP builtin 编译观察交接

- 日期、分支和基线：2026-09-27，wb03-source-ast，7621fc9。
- 目标：补齐真实HIP源码检查证据，中文回复，直接commit/push。
- 修改：既有builtin_value_probe新增固定hip-gfx1100 profile及配置；原CUDA默认不变。新增3项profile边界测试及证据记录。
- 实际执行：实录中的编译探测命令，会话63465退出0；O0/O2均成功，输入哈希稳定。报告在artifacts/wb-hip-builtin-probe-20260927-01/report.json，SHA256为1c430a65f1385692350d68f35b5db8cd896a6cccc40ac03f686d4ff6ac2dc2d3。
- 发现：quiet_NaN/infinity在合成HIP TU下lower为常量；写入和外部调用对照保留。匹配Clang23开发头尚未定位。生产HIP JSON builtin引用为lvalue，旧受限native checker要求prvalue。
- 没有执行：GPU、新候选部署、生产源码等价检查、远端CI核验。
- 实际回归：匹配AOCC原生插件启用，1215项CPU测试通过（92.164秒，无跳过），demo/diff通过。日志为/tmp/wb-hip-builtin-check.log及/tmp/wb-hip-builtin-demo.log。
- 边界：合成探针不提供生产调用原生身份；不拼接不同ASTContext指针ID，不把IR观察升级为无条件源码保证。
- 下一步：建立当前HIP编译器的匹配原生观测路径，再针对实际builtin引用形态补真实回归；旧CUDA插件不可直接加载Clang23。
- 提交安排：本轮实现、配置、测试与文档一起提交并推送；编译工件留本地artifacts。
