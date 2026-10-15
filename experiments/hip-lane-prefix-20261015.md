# 首次入口前缀的跨 x-lane 共同值

日期2026-10-15；基线`80fe671a7bf92a3745e73b5729e73c7236bf9eff`。
完整输入仍为冻结的手工HIP守卫候选，不是未经修改的上游生产TU。
本轮没有改HIP源码或运行GPU，也不宣布WB-03完整验收。

## 实际结果与边界

新增`lane_uniformity.check_prefix`在完整AST上顺序检查标量声明、赋值、
纯整数表达式和if控制依赖。只把精确API叶与参数的共同性作为外部前提，
派生局部值的共同性来自源码，不填人工uniform局部列表或数值域。

目标是kernel `0x7769241d57f0` 中`local_idx`的声明语句
`0x7769241ab5c8` **首次入口**，尚未执行这条声明。此前七条语句包含四个
constexpr声明、first_batch/local_batches初始化和上界裁剪。

两次fresh检查均`checked`，总重放26.098秒，运行前后检查器哈希一致：

| 选定变量 | 源码依赖，均为所声明族的共同输入 |
| --- | --- |
| first_batch `0x7769241aabe8` | workgroup size y、workgroup ID x、local ID y |
| local_batches `0x7769241ab178` | 上述三项及batch_size参数`0x7769241d5520` |

三条真实getter路径都经过静态property getter、`__hip_get_*`函数body，
最终到外部`__ockl_*`叶。**中间的`__hip_get_*`不是外部叶**；其body重新检查。
叶ID/axis分别是size `0x2d314cf8/1`、group `0x2d314340/0`、
local `0x2d313928/1`，声明签名为size_t(unsigned int)。返回类型取typed
CallExpr的去糖unsigned long；轴实参为int字面量经unsigned int转换。

[API协议](softmax-lane-prefix-api-20261015.json)明确标为UNVERIFIED：固定同次
调用、同workgroup和local y/z，变化local x；参数初值共同、精确API语义、
稳定性/无写入、property receiver和同target整数语义仍是外部前提。
不证明signed减法无溢出或unsigned→int数值保持，只证明定义良好执行中
相同输入经同一确定操作的相等关系。相同区间没有被用作相等证据。

尚未检查从该入口到outer/inner的存储保持，也未对齐实际外层i或消费后续
`batch_element_count=(i>=local_batches)?0:element_count`。现有加载组合未调用
这一入口；`count_common_across_lanes_checked`、实际参与、整核和部署均false。
26.098秒是CPU分析时间，不是kernel性能数据。

## 验证与复现

新增真实Clang回归覆盖int/uint轴、返回类型别名、MS property、值/引用别名、
共同写入、varying数据与控制依赖、两支常量赋值、无关分支写、target自身与
之后普通写/循环、逃逸/不透明调用、存储期、goto、协议错绑和身份冲突。
其中duplicate AST测试更新了协议root哈希后才检查身份层，非仅命中旧hash。
GPT-5.6 Sol编写测试并只读复核，主代理实现、运行真实重放与统一验收。

最终全量1434项631.042秒通过，退出0、无跳过；Clang17/23专项各6项通过，
分别2.343/2.413秒，退出0、无跳过。make demo和git diff --check通过。
以上为本地验收，没有核验本提交远端CI，也不是GPU数值验收。
本地目录`artifacts/wb-lane-prefix-20261015-01/`保存report.json、replay.py、
replay.log、clang17-final.log、clang23-final.log、check.log、demo.log。
大型AST与原始报告为ignored本地工件，不称本提交公开的完整复现包。

核心调用（无旧成功报告输入）：

```python
import json
from wavebridge.verification.lane_uniformity import check_prefix
root = json.load(open('artifacts/wb-hip-query-guard-candidate-20260930-01/native.json'))['payload']['ast']
api = json.load(open('experiments/softmax-lane-prefix-api-20261015.json'))
for declaration in ('0x7769241aabe8', '0x7769241ab178'):
    print(check_prefix(root, '0x7769241d57f0', '0x7769241ab5c8', declaration, api))
```

全量命令沿用[上一轮compiler-matched环境变量](hip-configured-loads-20261015.md)
运行`make check`，输出改为本轮目录`check.log`；`make demo`及`git diff --check`
单独运行。Clang17专项为`PYTHONPATH=src python -m unittest -v
tests.test_lane_uniformity_clang`；Clang23专项用同一unittest模块，将其CLANG变量
设置为`/home/husrcf/anaconda3/lib/python3.12/site-packages/_rocm_sdk_core/lib/llvm/bin/clang++`，
再用`defaultTestLoader.loadTestsFromModule`运行；不是native插件测试。

固定绑定SHA256：

- native文件：`df7d0b37e1d7ca16977f6d133285705d004a655e880b87b635148a373816e8b5`。
- root：`037b5ce0092111b2f87f3d5a92468fef7481188457fd10020e04337cc59bd86d`。
- report.json：`7b4c74175f8cd0fd4e74a6da9b3b0961de21d78d04727ca1b46225ba40e784ed`。
- lane_uniformity.py：`dfe08ddaece949212a2c898dec9c9cd10d6e03e93aa314edc44a36cd4643d448`。
- API协议：`6832ed926c149797c0e2e28515f4873187a88da751e2c3dabcc85e3dd488c982`。
- 测试：`3a219285a58420a5e838addbd73825d30ea4bb1f2207fba51635378fd79144fe`。
- fixture：`f2dcb7c633c72bd48248f4b62dac9e2fa4d3dee7268cc75c0e176e981e1e8fb6`。

下一步应fresh组合前缀、到loop使用点的保持及同一outer迭代下的0/n选择，
而不是直接把本报告的两个共同值标志写入既有加载报告。
