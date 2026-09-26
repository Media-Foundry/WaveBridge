# builtin 结构检查交接

- 日期、分支、基线：2026-09-27，wb03-source-ast，875635c。
- 约定：中文，验收后直接 commit/push 当前分支，不创建 PR。
- 完成：verification/builtin_calls.py 独立同次结构入口；5 项 fixture 回归；
  native Clang 文件扩至 6 项，GPT-5.6 Sol 负责真实测试并只读复核。
- 实际验证：make check 986 项、65.854 秒、native 插件启用、无跳过；
  make demo/diff 通过，日志 artifacts/wb-builtin-structure-UQL5sC/。
- 固定回放：上一轮 CUDA native envelope 上三个 builtin 子调用结构 checked，
  原始输入和报告 SHA 见 experiments/builtin-structure-evidence-20260927.md。
- 未执行：GPU、生产 TU 重采、远端 CI。没有新的整核/留出接受。
- 保证边界：native envelope 是可信输入而非认证来源；checked 仅同次身份及
  受限实参结构，值/效果语义未建立。写内存函数中的子调用结构成功不升级父级。
- 下一步：显式 builtin 效果/值协议与 wrapper/外围求值组合；上层绑定真实
  采集报告和工具链，不能单凭 builtin 名称或结构 checked 开放循环调用。
- 未提交/推送：本轮验收后统一提交推送；无外部阻塞。
