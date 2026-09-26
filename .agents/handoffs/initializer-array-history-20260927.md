# 数组调用接入初始化历史检查

- 日期、分支、基线：2026-09-27，`wb03-source-ast`，`0ec0785`。
- 用户目标：继续推进真实源码关系门控；中文回复，直接 commit，不创建 PR。
- 实现：`initializer_domain.check_to_statement` 接受精确绑定的数组检查请求，
  fresh 调用数组 checker，要求独立存储保持成立；成功子检查的假设传入父报告，
  未消费请求仍拒绝，失败调用保留 ID。协议见 `docs/contracts.md`。
- 回归：GPT-5.6 Sol 新增 `tests/test_initializer_array_history_native.py`，
  5 项真实 Clang/native 测试，覆盖合法数组写、全局写/未知调用、后续直接/引用写、
  错绑请求、伪造旧成功报告和未消费请求。不是生产 softmax 完整路径。
- 验证工件：`artifacts/wb-initializer-array-history-c8qvc6/check.log`、`demo.log`；
  最终计数见 `docs/status.md`。native 插件为 OqD1PQ 版本，编译器为 AOCC17。
- 未执行：真实 softmax 新 AST 完整历史链重放、GPU 作业、远端 CI 核验。
- 保证边界：仅目标语句首次正常进入前的条件值保持；外部效果、有效执行、
  存活和不别名前提仍未证明，整核/部署标记保持 false。
- 下一项：在 `wb-native-template-OqD1PQ/native.json` 上重新绑定 local_idx、
  最终输出循环与调用协议，重放完整历史；不能混用旧 AST 的 ID 或成功报告。
- 阻塞：没有需要用户提供的新输入。提交与推送状态以最终 Git 命令结果为准。
