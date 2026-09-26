# 次数界与列地址覆盖之间的验收边界

2026-09-27，基线 `bb97d7f`。本轮没有 GPU 作业，也没有扩充生产语料。
GPT-5.6 Sol 只读审查了 initializer/iteration、thread-start、column-domain
与 column-coverage 的连接边界；下面的 CPU 控制程序用于固定下一道门槛的
负例，不是这些检查器已对生产输出完成验证。

## 实际 CPU 负对照

```bash
/opt/AMD/aocc-compiler-5.1.0/bin/clang++ -std=c++17 -Wall -Wextra -Werror \
  experiments/probes/guarded_store_controls.cpp \
  -o artifacts/wb-guarded-store-controls-OTxYIu/controls
artifacts/wb-guarded-store-controls-OTxYIu/controls \
  > artifacts/wb-guarded-store-controls-OTxYIu/results.jsonl
```

程序退出码 0，六项预期断言均通过。所有操作均在分配的 CPU buffer 内；
“域外写”是超出逻辑列区间，不是故意触发 C++ 内存越界。

| 合成控制 | 工作次数 | 写入次数 | 缺列 | 重复写 | 逻辑域外写 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 正例，N=128，32 个不同起点 | 128 | 128 | 0 | 0 | 0 |
| store index + 1 | 128 | 128 | 1 | 0 | 1 |
| 每次工作双写 | 128 | 256 | 0 | 128 | 0 |
| N=129，循环头仍限 4 次 | 128 | 128 | 1 | 0 | 0 |
| 32 个起点中重复 0、缺少 31 | 128 | 128 | 4 | 4 | 0 |
| 缺少起点 31 | 124 | 124 | 4 | 0 | 0 |

源码 SHA256：`cfce5918cb51603993cba07385461b9e56b573033fb0160b76e576c9a92f58d4`。
binary SHA256：`44bca1706387fbaa7a30b354deb10944202c3b88fb3a488d5c6354d1ed76a84b`。
结果 SHA256：`a62ea5dbe1e2840137bb44d39c2e12830158c203246bfc68c4c050040f5b7766`。
编译器版本保存在同目录 `compiler.txt`，为本机 AOCC17 工具链。

这些控制只展示次数指标不能决定地址覆盖；没有运行 WaveBridge 的覆盖
组合器来宣称它存在错误放行，也不是新增真实 kernel 自动适配结果。

## 下一道门槛必须连接的事实

1. 从同一 AST 的 prefix/guard/header 建立实际列序列，例如
   `local_idx + it * WARP_SIZE`、`it=0..3` 与工作侧 `column < element_count`。
   不能只用每线程区间或 `[0,4]` 次数界替代精确关系。
2. 检查正步长、整数安全与有限 header 不截断：真实固定实例在 N≤128
   的前提下才有相应容量；N=129 的负例应被明确识别。
3. 参与者的起点多重集必须完整且唯一，且属于同一逻辑行。单个 getter
   在 `[0,31]` 内不证明集合等于 `{0,...,31}`；若集合仍来自外部协议，
   就明确保留外部来源，而不是从区间擅自补出 32 个线程。
4. 复用现有 residue coverage 数学核，同时绑定真实 work 中每条路径的
   store 次数、base 与地址。真实 softmax 的静态 false log 分支之外，
   仍有 sum==0 的两个互斥写入分支；不能用静态 store 总数等于 1 代替
   每条路径恰好一次。guard 中的 element_index 与 store 的实际下标、
   以及此前 dst 的偏移必须联系起来。

现有 `column_domain_check` 面向 kernel 顶层直接 For 并排除 break，且明确
只覆盖 induction 索引，不覆盖数据访问；不能直接宣布它已验证这份嵌套
softmax 输出。下一步应面向条件性的 fixed-row 逻辑地址覆盖与反例，
不再增加另一份仅重复次数上下界的报告。完整 row/launch 覆盖、动态对象
有效性、别名和数值结果仍是独立义务。
