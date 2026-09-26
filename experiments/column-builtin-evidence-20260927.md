# 条件调用效果进入真实列循环恢复

日期2026-09-27；基线8328e5e，分支wb03-source-ast。

## 新入口与验收边界

`recover_with_builtin_effects` 不接受成功报告，按精确调用ID与外部协议在同次
native AST上fresh检查完整调用点。只跳过已通过条件效果检查的调用子树，
所有父级存储目标、其它语句和分支照常检查。嵌套循环的自身递推及对外层
protected变量的复查都使用相同入口。默认recover仍拒绝调用。

独立父/子schema、外部前提保持性标记和external_call_effects_verified=false
防止旧组合checker误消费。partial调用成功不升级失败循环；全部恢复成功时
如存在未消费协议，父报告仍unknown并列明协议ID。

## 原有softmax的native前端重采

使用原`benchmarks/intake/pytorch-softmax-harness.cu`，从
`artifacts/wb-pytorch-softmax-KhwXBa/config.json`读取compiler与全部compiler_args，
调用native_captures.main，plugin为
`artifacts/wb-native-builtins-JR99CL/libwavebridge_capture_plugin.so`，timeout120秒。
采集报告保存完整实际命令、工具链/插件/直接源码前后哈希与同次依赖观测。
结果collected：artifacts/wb-column-builtins-twz82w/native.json（约756MiB），SHA256
`317b1a438bc13845cf76b5aa7461db4db2081b402c457a85c4160fdd7257c027`。

这是相同已暴露PyTorch生产头文件加既有人工harness，不是完整生产TU、blind
holdout或新代码谱系。新AST ID只在本次采集内使用，不与旧冻结AST直接拼接；
旧结果不覆写。没有GPU执行。

## 可重放的条件敏感性检查

```bash
PYTHONPATH=src python3 -m experiments.softmax_builtin_effects \
  --native artifacts/wb-column-builtins-twz82w/native.json \
  --output artifacts/wb-column-builtins-twz82w/recovery.json
```

输出路径须不存在；native报告哈希固定。自动沿精确callee与单返回body选择
三处可达huge_valf/nanf的路径，显式生成“未验证的开发敏感性假设”协议。
选择器不填写循环起点/步长/关系，也不提供成功结论；恢复器再次独立检查。
协议不因由脚本生成而得到认证，先前IR观察也不证明全部源码效果前提。
int_bits=32亦为显式外部ABI前提。

| 同一native AST上的模式 | recovered循环节点 | unknown循环节点 | 整体状态 |
| --- | ---: | ---: | --- |
| 默认recover，无效果协议 | 1 | 7 | unknown |
| 三处精确调用的条件协议 | 4 | 4 | unknown |

条件恢复对应上游行103、105、118、123，包含父/子循环，**不是四个独立kernel**。
行149、152仍call_effect_not_checked，行192、197仍unsupported_control_flow_in_body。
三处调用检查均checked，unused协议为空；入口ID为0x194e0d80。
source_program_checked/deployable仍false，未建立FP、完整参与或GPU语义。

结果SHA256：`4b209cf805ca46d40293a595b9d3c65a891a394e3a5111467c70f0e56b777ce7`。
报告记录driver与src实现前后哈希，inputs_unchanged=true。完整编译/运行环境
闭包仍不成立；导入的既有intake辅助模块沿基线版本使用。

## 回归

GPT-5.6 Sol新增真实Clang回归，覆盖默认拒绝/条件恢复、col及bound写入、引用
别名、其它未知调用、写global的wrapper、callee副作用、嵌套恢复及外层保护。
另外核对schema/flags隔离、错绑和未消费协议；没有把总测试数当形式证明。
