# 交接：局部贡献链与可扩展列覆盖

- 日期、分支、基线：2026-09-20，`wb03-source-ast`，`131bf04`。
- 用户约定：中文、直接 commit，无PR，未推送。
- 实现：`analysis/local_contribution.py` 恢复唯一顶层零初值累加器、相邻平方和循环及严格直接消费调用；`source.py` 接入并绑定实现哈希。前缀仅保存范围，消费者实参禁止副作用。
- 独立 checker：`verification/column_coverage.py` 检查相同步长序列的覆盖和重复，按余数排序，不展开列数；最后一次signed增量溢出unknown。无analysis依赖。
- 验证：`make check`176项通过，`git diff --check`通过。5625组小域枚举交叉验证，3584组小位宽逐步溢出模拟。真实Clang覆盖源码前缀、错误下标和额外更新。
- 真实HIP：沿用此前源码入口完整命令，输出目录为 `artifacts/wb03-source-contribution-01`。恢复consumer ID与自动发现的block helper相同；实现哈希核对一致。
- 条件列覆盖：该目录 `conditional-column-coverage.json` 绑定源码报告与checker哈希；777/4096/1000000000列均checked，但线程起点0～255为外部假设，不是自动恢复结果。
- 边界：prefix未分析；输入指针实际行归属、线程坐标、alias、浮点和外部intrinsic未建立，完整source checked仍false。没有新GPU运行或候选生成。
- 下一步：连接前缀的线程/行索引与列起点、归约结果的scale/输出写入，并检查host launch一致性。G1差异对照仍待完成，不能把局部进度宣布为整核门槛通过。
