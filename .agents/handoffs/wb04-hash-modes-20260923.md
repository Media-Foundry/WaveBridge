# 可选 canonical 哈希路径验收

- 日期：2026-09-23；分支 `wb03-source-ast`，基线 `5e19b6d`。
- 用户约定：中文、直接commit/push，不建PR，不合并master。
- 先收取原始完整TU任务退出0和77个实现哈希稳定结果，之后才修改实现。
  原任务结果与SHA见 `wb04-object-use-closure-20260923.md`，未丢弃或重启。
- 修改仅为 `integer_selection._hash` 的显式成本路径：默认streaming，
  opt-in one-shot；canonical参数一致。非法模式ValueError，MemoryError不回退。
- Sol只读审阅建议已纳入：显式streaming路径、内存失败传播、真实Clang
  正/负例完整报告一致性。另有2048个固定随机种子的嵌套JSON、Unicode/孤立
  surrogate、浮点/整数边界及非法JSON回归。

## 实际验收

```bash
export WB_NATIVE_CAPTURE_PLUGIN="$PWD/artifacts/capture-plugin-cleanups-gYQ3gz/libwavebridge_capture_plugin.so"
export WB_NATIVE_CAPTURE_COMPILER=/opt/AMD/aocc-compiler-5.1.0/bin/clang++
make check
WAVEBRIDGE_JSON_HASH_MODE=one-shot make check
make demo
WAVEBRIDGE_JSON_HASH_MODE=one-shot make demo
```

两种模式各638项、无skip，退出0；两个demo退出0。日志位于
`artifacts/wb-hash-cost-X3no77/check-{streaming,one-shot}.log` 与
`demo-{streaming,one-shot}.log`。新增定向18项也通过。
另运行 `PYTHONPATH=src python3 -m unittest discover -s tests -p '*clang*.py'`，
162项通过、退出0，日志 `clang.log`；没有将插件缺失的skip记为通过。
提交前的测试文件曾对旧实现产生预期TDD失败，保留为
`preimplementation-tests.log`；不将其混作最终通过记录。

## 范围与下一步

模式不进入canonical摘要；性能记录必须另记模式。本次未用新模式重跑完整TU，
不报告全组合加速比；较早单工件成本诊断不能代替该实验。one-shot分配完整
字符串和UTF-8缓冲区，非内存安全承诺，也不保证使用C encoder。
仅共用此函数的模块受影响，其他独立哈希不变。未知模式在部分上层转unknown，
在其他入口可能抛错，均不通过但错误接口未统一。
没有GPU执行、候选部署或整核证明。下一语义任务仍是受限复制效果与条件历史
保持，不可把显式引用闭合自动升级为值保持。
