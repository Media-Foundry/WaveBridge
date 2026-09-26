# 交接：首例浮点编译观察

- 日期、分支和基线：2026-09-26，wb03-source-ast，7799c05；开始时工作区干净。
- 用户目标：持续推进真实适配边界，中文回复，直接 commit 并推送当前分支，不建 PR。
- 完成：experiments/fp-compile-observation-20260926.md 保存 8 项实际编译结果、
  第 49 行局部 FMAC/分离乘加定位、复现命令和保证边界；docs/status.md 同步。
- 实际验证：python3 artifacts/wb-fp-ir-qZFn37/compile_matrix.py，8 次 device-only
  IR/assembly 编译均退出 0，8 个独立 driver dry-run 成功；make demo、
  git diff --check 通过。GPT-5.6 Sol 只读复核了产物哈希和局部 debug 映射。
- 原始证据：artifacts/wb-fp-ir-qZFn37/matrix/report.json，SHA256
  fee4e55f93d04a16299c0b4840e2fdf1db112678a2c76e7771247d5044ed563c。
  保存完整命令数组，没有独立 command_sha256 字段；产物/工具/输入有摘要。
  本地忽略工件不随 Git 推送；提交文档提供复现命令和固定输入描述。
- 没有执行：GPU、数值/性能测试、整套 826 项 CPU 测试、旧 AST 重放。
  本轮没有改变源码或 checker；826 是上一轮历史记录，不算本轮测试。
- 范围：源/候选默认局部更新都生成 FMAC，off 都生成独立乘加；两者仍不能
  证明实际局部值或整核等价。四份汇编都是 wave32，literal64 未获得运行授权。
  未调整冻结 baseline/tolerance，deployable 仍 false。dry-run 不证明实际
  子进程身份，完整 SDK/头文件/共享库闭包也未建立。
- 下一步：把实际 FP 编译配置和工件身份接入验收输入；不通过改成 off 偷换
  baseline。继续解决归约值与合法目标执行条件，保留独立谱系验收缺口。
- 提交状态：本交接与两份证据文档一起提交并推送 wb03-source-ast；不合并 master。
