# 新 native AST 上的 softmax 初始化历史重放

基线 `bc4e51c`，日期 2026-09-27；没有 GPU 执行或重新采集生产 TU。

```bash
PYTHONPATH=src:. python3 -m experiments.softmax_history_native \
  --native artifacts/wb-native-template-OqD1PQ/native.json \
  --leaf-protocol experiments/softmax-accessible-leaf-protocol-20260927.json \
  --output artifacts/wb-softmax-history-native-oyXP1v/replay.json
```

输入 native SHA256：
`a59c12247f796fe2034ba03ecc43782f77ac3942496b18a140ceacbb24c7ff45`。
shuffle 外部前提协议 SHA256：
`c9a085aa07bf43e2e3a9221dc92bce58b5237e9ddc4a1b9568ca454b1f065996`。
重放绑定全部 src 实现及 driver 依赖的前后哈希，不读取旧检查成功报告。

## 冻结选择与前提

沿用预先指定的 float/float/float/7/false/false 实例，函数 ID
`0x30d762e0`、local_idx 声明 `0x30ddbeb0`。冻结的函数体切片为
索引 8..19，初始化声明在索引 7，目标位于索引 20；最终循环 ID
`0x30de67f8`，外层 LoopHint ID `0x30de6830`。
最终 checker 独立重新绑定声明、目标与中间语句，并不信任 driver 的切片。

同次 AST 的静态布尔分支选择后，协议键为：

- `0x30ddd8f8`：infinity；
- `0x30de0078`：Max 数组归约；
- `0x30de1bc8`：exp；
- `0x30de47d8`：Add 数组归约。

这是开发期条件重放：getter `[0,31]` 是显式外部值域，不是 launch 或实际
线程坐标证明；infinity/exp leaf 的无写入及正常返回仍是 unverified 前提。
shuffle leaf 使用程序可访问存储保持前提，不声称全局无写入或同步正确。
Max/Add 分别重新绑定内部 shuffle 调用，不能复用另一个 helper 的成功结论。

GPT-5.6 Sol 只读复核未发现阻断问题。driver 递归遍历调用实参，若将来包含
嵌套调用可能多生成协议，最终 unused 门槛会保守拒绝；它不是通用协议推断器。
本案例已参与开发反馈，不是盲测独立谱系验收。

## 保证边界

无论局部结果如何，都不覆盖目标循环体、后续迭代、可达性、终止性、有效线程
参与、IEEE 数值等价、跨波宽改写或 GPU 部署。source/deploy 标记保持 false。

## 第一轮真实结果

`replay.json` SHA256：
`b21360614d7f5746e1d65daed95661c1a0ac9c42c070ab95c834ee33a7964f04`。
inputs_unchanged=true，结果 unknown/unsupported_body_effect。中间顶层索引
8..16 共 9 条通过，infinity 与 Max 调用均 fresh checked；索引 17 的
`acc_t sum[WARP_BATCH] { 0.0f };` 被保守拒绝。exp、Add 及最终未消费协议
门槛尚未检查。这证明 Max 已真正接入历史链，不表示目标入口已建立。

相同 capture 的原始声明摘录保存为 `sum-source-node.json`。Clang 的
InitListExpr 将 ImplicitValueInitExpr 与显式 FloatingLiteral 放在
`array_filler` 数组中，而没有 `inner`。不能只将 InitListExpr 加入白名单
后按 inner 遍历，否则可能跳过实际初始化副作用。

第一轮完整 1118 项测试通过（75.692 秒，native 启用、无跳过），demo通过；
该记录发生在后续 literal-array 支持修改之前，不代表后续修改已验收。

## 第二轮：受限数组初始化支持之后

同一命令仅将 output 改为 `replay-literal-init.json`，其 SHA256 为
`6c5e764901d93e296e852034c153a3c7b3bd88b209fb5e4ffc7d0a523313993f`。
inputs_unchanged=true，status=checked，索引 8..19 的 12 条顶层语句全部通过，
4 个调用均 fresh checked，unused_call_protocol_ids=[]。在显式前提下，
local_idx 的 `[0,31]` 保持到目标首次入口；目标循环体仍未检查。

这轮报告绑定的是补充 literal-array 支持、尚未补齐缺失/非字符串类型字段
防护的实现。负例发现该输入边界会抛 TypeError，随后改为保守 unknown，
定向 4 项真实 Clang/错形回归通过。不得将第二轮哈希冒充最终实现重放。
最终实现的重复运行使用 `replay-final.json`，其完成状态另行记录。

最终代码完整 1122 项测试通过（75.288 秒，native 启用、无跳过），
日志为 `check-final.log`；demo-final.log 对应演示通过，git diff --check 通过。
定向回归 4 项通过（0.038 秒）；GPT-5.6 Sol 另行只读复核和重跑亦通过。

## 最终实现重放（0faa378）

`replay-final.json` 已完成，SHA256：
`eca78b45ec85313ed7024b648d478871f3e4b3da5ffa14181cf5eb4d096ba533`。
status=checked，inputs_unchanged=true，12 条中间顶层语句、4 个调用通过，
unused=[]，条件 result_interval=[0,31]。结束后逐文件核对报告中的实现哈希
与当时工作树一致；随后才开始内层入口组合的实现。

本结论到外层输出循环首次入口为止。local_idx 的消费者在内层循环中，不能
未经检查就把该域用于内层每次入口：外层中内层前后语句以及循环头也须保持它。
