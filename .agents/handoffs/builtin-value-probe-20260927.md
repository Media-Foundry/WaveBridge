# builtin 编译观察交接

- 日期、分支和基线：2026-09-27，`wb03-source-ast`，`de786e0`。
- 用户约定：中文；验收后直接 commit/push 当前分支，不创建 PR。
- 完成：合成 CUDA 探针、固定配置/编译器的采集 driver、失败门槛测试；
  实录在 `experiments/builtin-value-evidence-20260927.md`。
- 实际验证：O0/O2 compile-only 均 observed，版本/直接输入与依赖清单已保存；
  原始证据在 `artifacts/wb-builtin-probe-jWB3VE/run-final/`。
- 完整验证：启用匹配 native 插件的 `make check`：975 项、66.352 秒、无跳过；
  `make demo` 与 `git diff --check` 通过。日志位于上述父目录。
- 没有执行：GPU、完整生产 TU 重采、机器码执行、远端 CI 核验。
- 范围：人工 IR 观察，不是源码或 lowering 证明；核心调用门控未放宽。
  依赖完整闭包、NaN/Inf 跨工具链语义、外围实参效果仍未建立。
- 子代理：GPT-5.6 Sol 只读核查 upstream LLVM 和本地工件；版本命令失败
  未进入状态门槛的问题已修正，并加入测试。
- 下一项：精确 builtin 身份/实参结构与显式外部语义协议；未知调用仍拒绝，
  不凭函数名、IR 常量或 O2 属性升级循环/整核接受。
- 提交状态：随本轮验收后提交推送；无 GPU 阻塞需要解除。
