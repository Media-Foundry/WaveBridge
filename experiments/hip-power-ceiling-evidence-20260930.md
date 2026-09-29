# HIP 输入相关幂次循环（2026-09-30）

基线9bac0a4，wb03-source-ast。新增verification/power_ceiling.py及真实Clang
fixture、测试；扩展现有host诊断的显式--power-input-domain选项。

## 检查方法与边界

从完整AST唯一函数声明精确匹配：int(int)、仅局部int counter=0、while
比较(1<<counter)<同一参数、每轮仅同counter++、直接返回counter。
所有访问按声明ID关联；多语句、写参数、static/TLS、错ID和<=拒绝支持。
参数按值、循环仅改counter，因此在显式1<=input<=2^(bits-2)域内，counter
依次为0,1,...，首次使2^counter>=input时退出。最大counter<=bits-2，
条件移位与递增保持在支持的非负signed-int范围内。
返回函数单调，区间端点为(lower-1).bit_length()和(upper-1).bit_length()。
这个规则不模拟移入符号位，不声称其它域全部是C++ UB；它们保持unknown。

checker不接受候选生成器成功报告，也不根据函数名识别log2。
调用实参、入口域、链接解析、后继移位、host历史与配置字段值均不在此保证内。

## 真实重放

```bash
PYTHONPATH=src:. python3 -u -m experiments.softmax_launch_native \
  --profile hip --host-dimensions --power-input-domain 65 128 \
  --native artifacts/wb-hip-native-20260927-01/native.json \
  --output artifacts/wb-hip-power-ceiling-20260930-01/report.json
```

输入SHA `46ac52b1c672fadd0e5a66bb3ab380373e0cd69929713d96e7010f375a0cd63e`；
报告SHA `318e3984f3fe830e483ebf2637e01803ca93acc3aba0d18b319ff1fa541bcdcf`。
输入/src/driver前后和结束后核对一致。原始大工件仅在本地。

沿minimum operand的shift→exponent变量初始化→直接调用候选选出helper
0x2246e440。它是源码定义检查，不是完成的call-site binding。
显式诊断域[65,128]下，唯一helper子检查checked，返回[7,7]、maximum_iterations=7。
该域是CLI提供的假设，没有从历史18个GPU样本或kernel模板参数反推。
call_domain_established=false，subsequent_shift_checked=false；整体数值域/lane/
源码/部署仍未建立。提供域而没有匹配helper时空清单表示未应用，不是通过。

下一步需要将输入域与确切host参数/调用绑定并检查到使用点的保持，之后才能
消费该函数结果检查后继移位。设备API返回域仍是独立义务。

## 验证

真实Clang正例覆盖改名、前/后++和单语句复合体；负例覆盖<=、额外修改参数、
static counter、错声明、重复函数、缺域、不支持范围和预算。小域枚举1…64与
直接递推一致，2…8位的支持边界也验证；不是完整编译器或GPU证明。
Sol只读审查未发现数学/AST误放行。无GPU、新生产源码采集或性能作业。
冻结最终代码后的make check：1286项、96.563秒、无跳过，日志
`/tmp/wb-power-ceiling-final-check.log`；定向12项通过，demo/diff通过。
native回归为SDK23/AOCC17匹配插件混合验收，不称全量SDK23。
