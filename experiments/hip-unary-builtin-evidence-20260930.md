# HIP 一元数学 builtin 身份与形参读取

2026-09-30，基线`62c96dc`。中断前的未验收修改在本轮续作，未新增GPU结果。

## 实际重放

```bash
PYTHONPATH=src:. python3 -u -m experiments.softmax_call_audit \
  --native artifacts/wb-hip-native-20260927-01/native.json \
  --using-shadows --unary-float \
  --output-dir artifacts/wb-hip-unary-builtin-20260930-01
```

固定输入SHA256：`46ac52b1c672fadd0e5a66bb3ab380373e0cd69929713d96e7010f375a0cd63e`。
输出report.json SHA256：
`d64b774471ad59da68a74b772db27144d236a5117fca07d11d0de21c4982f60b`。
退出0，observed，输入与记录的实现/driver依赖哈希前后一致。

| builtin | 原call ID | 读取的形参ID | 结构结果 |
| --- | --- | --- | --- |
| `__builtin_expf` | `0x204e0f28` | `0x204e0cf8` | checked |
| `__builtin_logf` | `0x204e7270` | `0x204e7040` | checked |

两个检查fresh消费受限UsingShadow身份规则，绑定原始普通节点、builtin声明、
native实参ID和按值float形参类型。结构为LValueToRValue→DeclRefExpr→ParmVarDecl。
默认模式仍不接受一元调用；模式与身份策略版本写入structure_policy哈希。

本次实际工件没有提供效果协议，没有检查exp/log外层wrapper链或重跑整个
循环恢复。checked仅是native身份和受支持实参结构；builtin无写入、正常
返回、数值值、FP环境、整核与部署均未建立。log出现在语法清单中不代表
当前非log-softmax实例实际执行它。

## 测试与审查

新增`tests/test_native_unary_builtin_clang.py`调用真实编译器匹配的插件，
6项通过（0.089秒）。普通expf/logf参数读取正例；递增、赋值、嵌套调用、
算术、引用、volatile、窄化、literal及非支持builtin保持unknown。
native元数据错绑、重复记录、声明/引用类型变形是明确标注的mutation负例。
显式外部效果假设的单调用组合只在测试里演示；它不认证实际HIP leaf实现。

所用SDK编译器：
`/home/husrcf/anaconda3/lib/python3.12/site-packages/_rocm_sdk_core/lib/llvm/bin/clang++`；
插件：`artifacts/toolchains/clang23-native-8f497e0/libwavebridge_capture_plugin.so`。
来源/构建身份沿用`clang23-native-build-20260927.md`。

GPT-5.6 Sol只读复核未发现P1或阻断提交的P2；这不是一般正确性证明。
没有运行GPU、没有重测18项历史pilot、没有核验远端CI。

最终1244项CPU测试通过（95.525秒，无跳过），make demo与diff通过；日志为
`/tmp/wb-unary-builtin-check.log`与`/tmp/wb-unary-builtin-demo.log`。全量中
新unary/using专项使用SDK23，既有native专项使用匹配AOCC17插件；不声称
全量SDK23验收。新增6项另在AOCC17匹配插件上通过（0.094秒）。完成后再次
核对重放报告中的src及driver依赖哈希与当前文件一致。

## 下一步

在同一原AST上连接wrapper形参转发与native leaf调用，独立检查外层实参，
然后才能在明确外部效果协议下讨论真实循环的条件保持性。不能直接将本次
leaf结构成功状态替换成整个exp调用成功。
