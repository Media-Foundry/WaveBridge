# 交接：属性检查接入坐标循环体保持门控

- 日期、分支与基线：2026-09-22，wb03-source-ast，d42f91f；中文回复，直接 commit/push，不创建 PR。
- 目标：不再以单个 blockIdx.x 属性 checked 代替整个循环体检查；保留旧源码恢复默认拒绝。
- 实现分工：用户指定的 Sol 子代理实现 `verification/column_body.py` 与私有 body
  遍历回调；主代理补真实 Clang 源码组合回归、协议说明及完整 TU 诊断。
- 检查对象：从完整 root 唯一函数和直接包含的唯一 ForStmt 重新观察坐标 header，
  取得 induction、边界及起点/步长 receiver 保护集合。逐节点检查 body，只有
  fresh property checker 通过的原始属性子树可以跳过内部遍历；普通写入仍受原存储规则约束。
- 输入边界：CompoundStmt body、1～8 个属性协议；完整扫描与每次 fresh property
  扫描均受显式节点预算约束。不是总时间或内存上限，无跨次可信缓存。
- 显式前提：root/function/loop 绑定的源有效性和无别名协议；每个属性仍要求
  receiver readiness/扩展语义、leaf 域/ABI/正常返回/无写协议，引用保持 unverified。
- 保证范围：仅 body 保持受保护声明，不是 body 无写，不证明 getter 每轮值稳定、
  header 整数递推、launch 域、覆盖、浮点等价或整核正确性；source/deploy 始终 false。
- 实际验收：`make check` 526 项通过；`make demo` 通过；
  `PYTHONPATH=src python3 -m unittest discover -s tests -p '*clang*.py'` 59 项通过。
  新真实 Clang 测试不 mock 恢复或 property checker；单独的 3 项 unit 中明确使用
  mock 验证回调和数量边界，不把它们视为源码证据。新增源码正例包括合法数组写入、
  多属性和只读 cast；负例包括隐藏引用、修改 induction/bound、下标 col++、
  不透明调用、逗号左值、静态 induction、嵌套上下文和错绑定/自签协议。
- 固定 TU 命令：`PYTHONPATH=src python3 artifacts/wb04-column-body-rLwd3x/replay.py`，
  退出 0，检查耗时 273.81 秒；完整扫描 3,705,324 节点，预算 4,000,000。
  函数 `0x3b019788`、循环 `0x7b148d1cfee8` 的 float 首个 body 条件 checked，
  属性 `0x7b148d1cfb58` 被 fresh 检查。七个相关实现文件前后哈希一致。
  此前 receiver/leaf 域协议原样沿用，source-validity/no-alias 是新增的明确诊断
  前提而非自动建立的事实；没有实际 launch 域或整核通过结论。
- 报告：`artifacts/wb04-column-body-rLwd3x/report.json`，SHA-256
  `9b2b7b8d73bebc6ad2a8806a6bf148fcc359489a5b595f4c4ba64cd509a33598`。
  原 AST SHA-256
  `5b612a12a1955a3db65467d16fb69c9df7501f29d828403cae0a38b8995afa4f`，
  未裁剪、未重写生产源码；不是新增 holdout 成功。
- 历史 CI：基线 d42f91f 的 run35738582192 success；不是本轮提交的 CI 结果。
- 未执行：GPU 作业、候选生成、性能实验或新的留出谱系验收。
- 下一步：绑定实际 launch/坐标域与 unsigned 递推检查；Half/BFloat16 的转换调用
  仍需明确分析，不可用 float 路径的局部结论替代。
- 提交安排：完成验收后提交并推送当前工作分支；大型原始诊断工件保持本地忽略。
