# 交接：静态成员调用证据

- 日期、分支和基线：2026-09-20，`wb03-source-ast`，`17e244b`。
- 用户约定：中文、直接 commit、不创建 PR；未推送。
- 修改：归约发现器仅允许精确同 root `CXXMethodDecl` 且明确 `storageClass=static` 的成员调用；保留 receiver，拒绝 virtual/缺声明/不明确 static。新增真实 Clang property fixture 与动态派发拒绝测试。
- 实际验证：`make check` 161 项通过，`git diff --check` 通过。
- HIP 复验：沿用上一份交接的完整 `wavebridge.source` 命令，仅将输出目录改为 `artifacts/wb03-source-static-members-01`。源码与 SDK compiler 不变；报告实现哈希与当前代码一致。
- 结果：13 个可达定义、4 条 static member 边、1 个 block 和1个 XOR 候选；21 条未解析调用诊断，分析完整性 false。原始 AST 和报告保存在上述目录，未覆盖旧证据。
- 保证边界：只建立调用关系，不解释 getter 返回值为线程坐标；receiver/转换/外部接口仍未证明。未执行新的 GPU、MI250、native64 或性能实验。
- 下一步：检查17条 callee cast 的真实种类及声明来源，按所需语义建立有边界的外部接口接入；不以减少 unknown 数量代替整核关系验证。
