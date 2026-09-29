# HIP 调用与紧邻移位（2026-09-30）

基线dedb0f5，wb03-source-ast。新增power_ceiling.check_initialized_shift，
沿唯一同块相邻DeclStmt检查plain自动int指数与int/const int幂值初始化。
第一个initializer必须精确direct int(int)调用，实参为指定plain-int声明的
直接读取；第二个必须为`1 << 同一指数`。重新检查函数体，不能传旧子报告。
相邻声明排除了普通中间语句改写；不覆盖后续历史或异步干扰。

## 真实重放

```bash
PYTHONPATH=src:. python3 -u -m experiments.softmax_launch_native \
  --profile hip --host-dimensions --power-input-domain 65 128 \
  --native artifacts/wb-hip-native-20260927-01/native.json \
  --output artifacts/wb-hip-initialized-shift-20260930-02/report.json
```

输入SHA `46ac52b1c672fadd0e5a66bb3ab380373e0cd69929713d96e7010f375a0cd63e`。
最终02 SHA `5095b0bc52a33b6a1ebb51c061f2183e2c8a707a2d1c38cc4373b142955d0569`。
输入/src/driver前后稳定且结束后复核一致。大工件仅在本地artifacts。

参数0x225088a8在调用0x745c57a5b620的读取点处于[65,128]是显式外部前提。
callee精确为0x2246e440，指数声明0x745c57a5b580，后继幂声明0x745c57a5b680。
fresh条件检查得到指数[7,7]、指数保持到紧邻shift、幂初始域[128,128]。
argument_domain_verified=false，链接解析与后续历史未建立；不能将CLI域
当成从host入口或GPU样本证明的域，也不能据此推导完整block或lane范围。

## 首轮未通过与局部修正

01 SHA `f3a77f0d9314548c9337703d588ae2e5328b06c4b0dcdad35b89897743fe8192`，
初始化shift子报告unknown/selected_identity_not_unique，保留未覆盖。
读原AST发现base IntegerLiteral 0x2247e980在模板/实例中有两份完全一致记录。
新规则仅在唯一父shift的base位置接受无children、完整字典相等的整数字面量
副本，并继续检查int/prvalue/value=1。报告绑定root hash、策略与occurrences=2。
其它声明、调用、父表达式与存储引用仍要求唯一；冲突副本拒绝。不全局去重AST。
修正后fresh执行02，不改写01。

## 验证与下一步

真实Clang正例覆盖adjacent调用/shift；负例覆盖中间修改、底数2、读取另一
变量、static指数、错误实参、缺域。结构变异另验证一致字面量副本、冲突副本
与重复声明；这些变异不是新增真实工作负载。定向16项通过。
Sol两轮只读复核无阻断。支持plain int指数，const指数保守未知；call域和
实际链接实现仍是显式前提，不称端到端验证。无GPU、新采集或性能作业。
下一步需把此读取点域接到冻结输入协议及host调用历史，同时独立处理设备
API返回值和幂值到minimum更新点的保持；不能直接手填对象配置域。
最终make check：1290项、98.563秒、无跳过，日志 `/tmp/wb-initialized-shift-final-check.log`。
SDK23/AOCC17匹配插件混合验收，非全量SDK23；demo/diff通过。
