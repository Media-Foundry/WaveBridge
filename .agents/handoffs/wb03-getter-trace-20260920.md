# Getter 证据完整性与精确 ID 歧义

- 日期/分支/基线：2026-09-20，wb03-source-ast，3cd118b；起始工作区干净。
- 用户约定：中文、直接commit、阶段性验收后push，不创建PR。
- 完成：return_trace保存每步原始return/callee AST、调用类型、声明种类/签名/
  storageClass及中间成员receiver。重复exact ID返回unknown，禁止静默覆盖。
  Sol子代理只读核对实际getter与改动，意见已纳入说明和冲突节点顺序负例。
- 验证：`make check` 315项；`git diff --check`。
- 真实源码命令：
  `PYTHONPATH=src python3 -m wavebridge.source benchmarks/cases/llama-rmsnorm/baseline/rmsnorm_logical32.hip.cpp --compiler /home/husrcf/Code/ProtBind/wavebridge/artifacts/toolchains/sdk-view-sx4rmd37/bin/hipcc --compiler-arg=--cuda-device-only --symbol rms_norm_f32_logical32 --int-bits 32 --output-dir artifacts/wb03-getter-trace-01`
- report SHA256：`20cb521a751cf3634cecff8cedb0bb9f45103366f519464635dd4f79a98f5f74`。
- AST SHA256：`e445291c656b0e2fab762f42d6fb1992efecfcbdc11ad8fa2434dfd9c6c96705`。
- 结果：真实起点getter追踪external_leaf，两个wrapper均static；保留size_t→unsigned
  int转换、完整调用表达式，不赋予external leaf任何自动坐标语义。
- 未执行：GPU数值、性能、源/目标关系验证；临时AST工件仅在本地ignored目录。
- 保证边界：只检查exact ID节点唯一，不解析不同ID的重声明链。raw MemberExpr
  children不是receiver纯度证明。checked/deployable始终false。
- 下一步：建立受限pseudo-object初始化值连接；绑定显式外部local-id轴协议及
  launch域，逐转换验证size_t→unsigned int→int值保持，不能靠函数名猜线程语义。
- 提交前所有修改仅为本交接列出的实现、测试和文档；提交后按用户授权推当前分支。
