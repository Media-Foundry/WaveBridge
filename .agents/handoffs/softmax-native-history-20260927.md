# 真实 softmax 初始化历史重放

- 日期、分支、基线：2026-09-27，`wb03-source-ast`，`bc4e51c`。
- 目标：继续源码关系门控；中文回复，直接 commit/push，不创建 PR。
- 完成：新增 `experiments/softmax_history_native.py`，在固定新 native AST 上
  重新绑定初始化、最终输出循环和全部实际消费的调用协议；不复用成功报告。
- 实测第一轮：unknown，越过 Max，卡在 sum 数组初始化。
- 实测第二轮：增加受限 float 数组初始化槽位检查后，12 条顶层语句和
  4 个调用均 checked，unused=[]，条件 local_idx 域 `[0,31]` 保持至首次入口。
- 随后补齐畸形类型字段的 unknown 防护，4 项定向测试通过，GPT-5.6 Sol
  只读复核无阻断。最终完整测试计数见 `docs/status.md`。
- 工件和精确命令：`experiments/softmax-native-history-evidence-20260927.md`；
  日志位于 `artifacts/wb-softmax-history-native-oyXP1v/`。
- 最终代码另启动 `replay-final.json` 重放，启动时进程句柄为 76230；本条仅为
  定位提示，不证明进程仍运行。继续前须用实际句柄/结果重新核实，不能因
  ps 看不到跨工具会话进程就重新启动。第二轮报告不是最终实现哈希的报告。
- 没有执行 GPU、跨波宽变换或远端 CI 核验。外部 getter/leaf 效果、有效执行、
  存活和不别名前提仍未证明；目标循环体、后续迭代和整核结论仍缺失。
- 下一项：确认最终重放结果；然后把 fresh 历史入口域与同一 AST 的循环边界
  检查显式组合，不能直接把旧 loop-entry 假设改成“已证明”。
- 未提交/推送状态以 Git 命令结果为准；没有需要用户输入的外部阻塞。
