# 交接：数组helper写入范围

- 日期、分支、基线：2026-09-27，wb03-source-ast，8a299ae；起始工作树干净。
- 用户目标：中文协作，按门槛推进；直接commit并推送当前分支，不建PR。
- 完成：array_call_effects.py受限checker、5项真实Clang回归、固定Softmax
  replay driver、实验实录和docs/status.md。GPT-5.6 Sol负责测试及独立复核。
- 实际命令：`PYTHONPATH=src:. python3 experiments/softmax_array_effects.py
  --native artifacts/wb-column-builtins-twz82w/native.json
  --output artifacts/wb-array-effects-aUY5oM/replay.json`；原生插件/编译器环境
  与前轮相同的`make check`，1083项通过，73.363秒，无跳过；make demo和
  git diff --check通过。原始日志在同一目录。完整输入/输出哈希见实验实录。
- 结果：7处静态写入已分类；5项调用/生命周期义务仍unknown，不能提升为
  protected_storage_preserved。输入与实现前后哈希一致。
- 未执行：新GPU、生产TU重采、远端CI核验；尚未接入历史保持checker。
- 前提：源码执行有效、正常返回、数组与保护对象存活且不同、所有数组访问
  在对象内及无异步干扰。没有数组边界/浮点/归约/通信正确性或部署保证。
- 提交范围：本轮checker、测试、driver、实录、状态和本交接；不纳入大AST。
- 下一步：独立检查实际Max::operator()、构造/生命周期与shuffle/defaultarg
  效果，再接历史保持。不能给写数组归约签发虚假的全局无写假设。
