# 从次数界转向实际列地址覆盖

- 日期、分支、基线：2026-09-27，`wb03-source-ast`，`bb97d7f`。
- 目标：继续真实源码门控，中文回复、直接 commit/push，不创建 PR。
- 当前真实重放：句柄 49280，工件目录
  `artifacts/wb-softmax-derived-bounds-EobLZf/`。本轮已多次实际轮询仍存活；
  后续必须重新核实，不把本记录当作存活证明，不因 ps 命名空间缺失重启。
  核心 src 和 driver 依赖在运行期间保持未修改。
- 本轮完成：独立只读审查次数/完整 lane 集合/实际 store 地址之间的缺口；
  新增 `experiments/probes/guarded_store_controls.cpp`，AOCC17 -Wall/-Wextra/
  -Werror 编译并实际 CPU 运行通过 6 项预期。工件位于
  `artifacts/wb-guarded-store-controls-OTxYIu/`，精确命令和哈希见
  `experiments/guarded-store-controls-20260927.md`。
- 没有将合成控制登记为生产 kernel、GPU 结果或 checker 错误放行；没有
  新增 Python checker 或将次数界升级为覆盖。此前 1132 项测试属于 bb97d7f。
- 下一步：先收取运行中真实重放与实现哈希；然后连接真实 guarded column
  序列、header 非截断与每路径唯一 store/base/index，复用 residue coverage。
  参与者集合若仍来自外部协议必须明示，不从单线程区间补出完整 lane 集合。
- 关键负例已实际执行：偏移 store、双 store、N=129 截断、重复/缺少起点。
  不继续叠加仅报上下界的模块。完整 row/launch、动态对象/别名、FP 值与
  部署仍是独立义务。
- Git 提交/推送以实际输出为准；无用户输入阻塞。
