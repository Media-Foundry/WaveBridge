# 外层到内层入口保持

- 日期、分支、基线：2026-09-27，`wb03-source-ast`，`0faa378`。
- 目标：继续真实源码关系门控；中文回复，直接 commit/push，不创建 PR。
- 上轮最终重放已结束：`artifacts/wb-softmax-history-native-oyXP1v/replay-final.json`
  checked、inputs_unchanged=true，SHA256
  `eca78b45ec85313ed7024b648d478871f3e4b3da5ffa14181cf5eb4d096ba533`。
  结束后先核对实现哈希与 0faa378 工作树一致，随后才改核心。
- 本轮实现：`initializer_domain.check_nested_entry` 与私有 work worker 组合，
  fresh 历史、精确源声明保护、outer header/prefix/guard、全部 outer work、
  嵌套 ancestor 保护及选定 inner 路径；不接受旧成功报告。
- GPT-5.6 Sol 新增 5 项真实 Clang 回归并只读复核。完整 1127 项测试通过
  （75.954 秒，native 启用、无跳过），demo/diff 通过。
- 实际命令、前提和工件：`experiments/softmax-nested-entry-evidence-20260927.md`。
- 真实 nested-entry 重放启动句柄为 62096，输出目录
  `artifacts/wb-softmax-nested-entry-ujZgP9/`。继续时须实际轮询句柄或检查终态；
  本文不是存活证明，不因 ps 看不到跨会话进程就重新启动。
- 未执行 GPU、跨波宽或远端 CI；外部 getter/leaf、有效执行与无别名前提
  保留。每次实际到达的入口域保持，不等于可达性、次数、整数安全或迭代域。
- 下一项：收取本次真实重放，再把 fresh 入口域与同 AST 内层循环边界检查
  显式组合。local_batches 等外部输入域未解除。
- 提交/推送以实际 Git 输出为准；无用户输入阻塞。
