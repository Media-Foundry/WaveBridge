# 错误检查包装的正常返回必要条件

基线 `05d41c4`，分支 `wb03-source-ast`。本轮没有 GPU 执行。

`normal_return_guard.check` 从完整 AST 检查唯一参数、唯一顶层 if 的窄函数。
条件为参数普通加载与枚举常量分别转换为 int 后的 builtin `!=`；失败分支
仅有调用表达式，最后一个按精确声明绑定到携带 noreturn 类型契约的直接调用。
函数内拒绝 return、goto、statement expression、汇编、异常处理、lambda 等
不支持的控制流。已有 using-shadow 身份规则原样复用，不全局去重 AST。

在有效 C++、普通顺序执行、无非局部跳转/异步干扰且链接实现遵守 noreturn
声明契约的前提下，包装函数正常返回意味着**这一转换后比较为假**。不证明
函数必然返回，不证明原枚举值相等，不证明 API 成功，也不建立属性数值域。
日志调用不被假定为纯函数；若它抛出或不返回，正常返回条件没有成立。

driver 从已检查字段快照 helper 的原始前缀选出直接一实参调用，记录调用 ID、
原始实参 AST 和 fresh 包装检查。这里的 query 实参记录仍是语法绑定，
不是 API 参数、输出对象或运行库语义验证；各调用是否正常返回亦未证明。

## 重放命令

```bash
PYTHONPATH=src:. python -m experiments.softmax_launch_native \
  --profile hip --native artifacts/wb-hip-native-20260927-01/native.json \
  --output artifacts/wb-hip-return-guard-20260930-01/report.json \
  --host-dimensions
```

固定输入 SHA256：
`46ac52b1c672fadd0e5a66bb3ab380373e0cd69929713d96e7010f375a0cd63e`。

定向命令：

```bash
PYTHONPATH=src python -m unittest discover -s tests -p test_normal_return_guard_clang.py -v
```

真实 Clang 正例与负例、重复身份、预算和不修改输入回归已加入；完整测试和
实际 HIP 重放结果以验收补记为准。本轮不解除整核或部署门槛。

## 实际验收补记

上述重放完成，inputs_unchanged=true。报告 SHA256：
`c1be9285f29ed9f86f79a7c98b3f0541a10a91b479c770c4bc88a9ab49e07dc3`。
两个前缀调用 `0x220430c8` / `0x22043958` 的实参分别为
`0x22043000` / `0x220432d8`，均绑定包装函数 `0x22040860`。
两份 fresh 包装子报告 checked；比较 `0x22040a28`，noreturn 声明
`0x1ff01710`，末尾调用 `0x22040e98`。声明重复引用按既有规则核对两处
using-shadow 扩展，仅允许声明根 loc.file 省略，原始 AST 未改写。

完整 `make check`：1315 项，99.514 秒，无跳过；日志
`/tmp/wb-return-guard-check.log`。运行环境沿用前轮：visibility、unary builtin、
using-shadow 使用 SDK Clang 23 及匹配插件；旧 native capture 使用 AOCC Clang 17
及匹配插件，普通 fixture 使用 PATH clang++。`make demo`、`git diff --check`
通过。GPT-5.6 Sol 只读复核未发现阻断性问题；报告记录精确 function ID、root
hash、identity policy 和 driver 实现哈希，但尚无单独 selection/policy hash。

后续应绑定查询结果与包装形参的传递，再对 API 成功/输出字段引入可核查的外部
协议；不能把本次比较必要条件当成已完成的 API 语义证明。
