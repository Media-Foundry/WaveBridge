# 交接：可复用的 device-only FP 编译采集

- 日期、分支、基线：2026-09-26，wb03-source-ast，f175743，开始时工作区干净。
- 用户目标：持续推进真实适配；中文回复；直接 commit、定期推送当前分支，不建 PR。
- 完成文件：frontend/device_compile.py 新增固定 O2、显式 target/contraction 的
  IR/汇编采集与 CLI；tests/test_device_compile.py 是 GPT-5.6 Sol 协作实现的
  9 项 mock 回归；frontend README、architecture、status 同步边界与工件索引。
- 实际验证：匹配 native 插件启用的 make check 最终 835 项通过，64.289 秒；
  make demo、git diff --check 通过。首次全量读到测试中间版本，1 项 mock
  缺 command 失败；固定后重跑全量通过，不删除初次失败记录。
- 真实编译：固定源和 literal64 候选 default/off 各一次入口，共 8 个实际
  HIP 编译成功，另外保存单独 dry-run。四个目录及 report SHA 在 docs/status.md。
  artifacts/fp-compile-bi8gy8eo/ 保存 check.log、check-final.log、
  collector-tests.log、demo.log。工件被忽略，不随 Git 推送。
- 编译器：/home/husrcf/anaconda3/bin/hipcc；target gfx1100；协议为固定
  benchmarks/cases/llama-rmsnorm/protocol.json；重放命令见 frontend README，
  实际完整命令见各 report.json。collector SHA 与编译报告核对一致。
- 没有执行：GPU、数值/性能比较、旧 AST 关系重放；没有改动 baseline/tolerance。
- 保证范围：compiled 只是非空输出与零退出及直接输入前后哈希；不验证协议
  内容或输出语义，不证明 lowering、FP 等价、实际 wave 或部署安全。工具链
  dry-run 独立于编译；头文件/共享库/环境未冻结。始终 deployable=false。
- 下一步：消费已绑定的实际编译配置与工件，连接冻结协议下的数值验收；不能
  把哈希采集自身当作门控通过。native64 合法执行环境和归约值保证仍未建立。
- 提交状态：上述文件形成一个验收提交，推送 wb03-source-ast，不合并 master。
