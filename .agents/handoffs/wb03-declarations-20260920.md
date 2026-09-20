# WB-03 声明接入交接

- 基线 `2608e55`，分支 `wb03-source-ast`；中文、直接 commit、不建 PR。
- 新增 full-translation-unit 采集选项及声明精确 ID 索引；stub、不匹配 ID 和跨 root 不拼接，previousDecl 不跟随。
- 实际 HIP 完整 AST/索引在 `artifacts/wb03-tu-hgtXLo/`；有效文件为 `rmsnorm-tu-single.json`、`rmsnorm-index.json`。前两次失败的 JSON 不能作为输入。
- 常量 initializer 与 helper body 在同次 AST 中存在；完整索引仍有 2 个 unresolved。尚未求值常量或解释 HIP 属性 getter。
- 修复大 AST 序列化内存峰值；完整模式仅保留解析树和原 stdout 哈希，非 verbatim stdout。哈希计算采用流式 canonical JSON。
- `make check` 98 项通过；完整 HIP 采集不执行 GPU kernel，不证明关系恢复或 G2 完成。
- 下一步：从入口限定可达声明，求值受支持常量表达式并解释线程 getter 的真实定义，接到列分配和 collective 路由关系。
