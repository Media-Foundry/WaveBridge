# softmax提前退出结构检查

2026-09-27，wb03-source-ast，基线b305043。无GPU、无生产AST重采。

```bash
PYTHONPATH=src python3 -m experiments.softmax_exit_guards \
  --native artifacts/wb-column-builtins-twz82w/native.json \
  --recovery artifacts/wb-loop-calls-SIr4BJ/all-calls.json \
  --output artifacts/wb-exit-guards-hO8EFa/replay-contextual.json
```

选点来自历史unknown循环的精确range，在同一固定entry内核对唯一ForStmt；
checker再独立检查完整AST，不读取人工退出关系。

首次全局statement-ID唯一性版本拒绝两处循环，虽然四个guard操作数均checked。
保留原始失败artifacts/wb-exit-guards-hO8EFa/replay.json，SHA256：
`c0671f32b2da78c05f47d195430d454ca0930352deb8a9492aec2bc600e65e1b`。
原生AST中offset8280的BreakStmt `0x1916dac8` 和offset8967的`0x1916efe0`
各出现12次：模板AST共享语句身份，不等于同一动态退出事件。

当前改为root哈希＋唯一loop ID＋子节点路径绑定结构语句，guard/操作数仍保持
精确语义检查。真实Clang的两个模板实例回归独立复现共享BreakStmt ID；
重复loop/guard的合成冲突fixture仍unknown。没有将身份冲突默认当成无副作用。

最终replay-contextual.json：两项均checked，分别为leading_break_guard及
trailing_else_break；inputs_unchanged=true。SHA256：
`0f368af36aba91233accabddd8fafbd582310f328a49f8de13515cbd684c6777`。
外层guard为`i >= local_batches`，true退出、无prefix；内层为
`element_index < element_count`，false退出、prefix为索引声明。
前者BreakStmt相对路径[4,0,1]，后者[4,1,2,0]，均须结合各自loop和root哈希。

最终make check：1035项通过，69.179秒，匹配native插件、无跳过；demo/diff通过。
日志check-final.log与demo-final.log保留。GPT-5.6 Sol实现7项Clang/边界回归
并复核；远端CI未核验。

结构分区不是有效bound/coverage证明：末尾else-break之前的prefix即使在退出
迭代也执行；prefix/work效果、guard值与稳定性、循环头、整数域均未建立。
历史6/8循环恢复结果不升级，整体仍unknown；不是新holdout、整核或部署证据。
