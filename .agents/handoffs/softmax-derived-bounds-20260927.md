# fresh 入口域到内层次数边界

- 日期、分支、基线：2026-09-27，`wb03-source-ast`，`563da13`。
- 目标：持续推进真实源码门控；中文回复，直接 commit/push，不创建 PR。
- 上轮 nested-entry 重放已完成：`artifacts/wb-softmax-nested-entry-ujZgP9/replay.json`
  checked、inputs_unchanged=true，SHA256
  `1ec6113783beb452f4bf4cbe386af712df2cd98dc8bb55a50a62282e52a683bc`。
  local_idx 域 `[0,31]`，inner `0x30de6780`，路径 `[4,2,1]`，两组 unused=[]；
  结束后先核对逐文件实现哈希一致，再修改核心。
- 本轮实现：`check_nested_iteration_bounds` fresh 运行入口链并注入源域，
  禁止 caller 覆盖，独立检查内层次数界；其余外部区间仍须在该次入口成立。
- 新增外部协议按形参位置 4/name/type 绑定既有 element_count `[0,128]`
  示例域，不假装是源码自动校验或 launch 证明。
- GPT-5.6 Sol 新增 5 项真实 Clang 回归并复核。初始 fixture 分区不支持的
  失败日志保留；改用现有支持分区后正例 `[1,4]`、溢出及错绑等验收通过。
- 全量 1132 项测试通过（76.736 秒，native 启用、无跳过），demo/diff通过。
  工件：`artifacts/wb-softmax-derived-bounds-EobLZf/`；实际命令和范围见
  `experiments/softmax-derived-bounds-evidence-20260927.md`。
- 真实新重放启动句柄 49280；继续前实际轮询，本文不是存活证明。运行期间
  不修改实现或 driver 依赖，避免哈希失配；不可因跨会话 ps 缺失而重启。
- 未执行 GPU/远端 CI。单次 reached inner invocation 的次数界不是 outer
  总工作量；外部 leaf、有效执行、无别名等条件及完整覆盖/等价仍未解除。
- 下一项：收取真实 derived-bounds 报告，再按实际未解除义务推进源循环关系；
  不将次数区间自动升级为精确覆盖或可部署适配。提交/推送以 Git 输出为准。
