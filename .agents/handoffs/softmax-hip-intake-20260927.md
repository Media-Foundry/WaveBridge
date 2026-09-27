# 实际 HIP 工件源码接入交接

- 日期、分支和基线：2026-09-27，`wb03-source-ast`，基线`58695d0`。
- 用户目标：推进真实源码到检查链；中文回复，直接commit并推送，不创建PR。
- 已完成：`experiments/softmax_hip_intake.py`绑定最终W7900 pilot的输入与工具链，重新采集完整HIP AST；新增3项绑定测试、结果索引、证据实录和状态更新。
- 实际验证：证据实录中的采集命令成功；`make check`启用匹配AOCC原生插件，1208项通过（92.433秒，无跳过）；`make demo`、`git diff --check`通过。
- 工件：`artifacts/wb-softmax-hip-intake-20260927-01/`；report SHA256为`e0f3691cd2a4952193770cf251e7414d2be9ea4af11b4776967f7e0da9e091b9`。
- 观察：334个依赖文件；执行源码逐hash绑定；默认循环恢复1/8，归约发现21处调用未解析、0个XOR候选；选定实例1处launch，另22处未解析位置保留。
- 没有执行：本轮GPU、性能测量、跨波宽适配、远端CI核验。
- 保证边界：不复用CUDA sm80报告；整数ABI仍为外部假设；原binary完整依赖闭包未建立，source_program_checked/deployable仍false。默认恢复覆盖不代表所有条件checker的能力上限。
- 提交安排：上述实现、测试及文档作为同一提交推送当前分支；大体积原始工件保留本地，不入Git。
- 下一项：在新HIP AST上复用已有模板/static-branch和条件效果检查，逐项定位实际拒绝点并连接唯一launch；不按kernel名字注入关系模板。
- 阻塞：本次交付无阻塞；完整语义恢复与自动适配仍待后续工作。
