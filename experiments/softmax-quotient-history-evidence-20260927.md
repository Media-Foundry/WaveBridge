# quotient 初始化到 threads 声明入口

2026-09-27，基线 `3f28984`。本轮把已有条件quotient关系连接到较晚声明入口，
并抽取minimum与quotient共用的私有历史检查，避免复制第二套存储用途规则。

## 边界

`check_quotient_to_statement` fresh执行quotient初始化检查，再保护quotient
本身。共用helper的初始化模式要求起点是唯一VarDecl的DeclStmt，不把该
initializer子树作为任意写入豁免；初始化关系只能由前一步精确检查建立。
全函数引用闭合包含array_filler，中间语句另检查效果。minimum旧入口继续
采用原模式，保证范围不扩展。

通过仅指目标语句首次入口仍具有已建立的条件quotient关系，明确保持
`target_statement_checked=false`与`division_safety_established=false`，非零
义务原样传递。没有建立构造参数求值、整数转换、字段域、复制或启动保证。

GPT-5.6 Sol完成5项真实Clang回归及只读复核，覆盖outer else内端点、零间隔、
quotient自身重写、引用/地址逃逸、opaque调用、跨block/反序、static和预算边界。
正例明确检查保护声明是quotient而非denominator。主树专项复跑5项通过
（0.137秒）；相邻minimum历史和quotient初始化也已定向复验。

## 重放

```bash
PYTHONPATH=src:. python3 -m experiments.softmax_launch_native \
  --native artifacts/wb-native-template-OqD1PQ/native.json \
  --output artifacts/wb-quotient-history-check-NMmHiQ/replay.json --host-quotient-history
```

工件与验收日志位于 `artifacts/wb-quotient-history-check-NMmHiQ/`。未运行GPU。
完整1179项通过（93.128秒，native启用、无跳过），demo/diff通过。

## 真实结果

原会话96750正常结束，`host_quotient_history_check.status=checked`，
`inputs_unchanged=true`，结束后核对实现与driver依赖逐文件哈希一致。
报告SHA256：`20ca8983048289ed45f7a077a935368b66f85c0bdaaacc44068508473dbcf9f7`。

共同block `0x30d7b918` 内，quotient声明语句`0x30d69830`位于child6，
threads声明`0x30d69d50`位于child9。保护声明为warps_per_block `0x30d696c0`，
两条中间语句通过、两个值读取用途闭合。到threads声明入口仍具有
`trunc_toward_zero(128/min(before_operands))`这一条件关系。
非零除数义务未解除，构造语句内部未检查，不是合法dim3或launch的验收通过。
