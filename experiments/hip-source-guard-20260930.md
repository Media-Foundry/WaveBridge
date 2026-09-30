# 同次查询后的源码运行时守卫

基线`79d975d`，分支`wb03-source-ast`。本轮生成隔离候选并重新采集完整HIP AST；
没有执行程序/GPU，没有改变原历史基线输入。

## 候选与保证范围

`experiments.softmax_query_guard`要求三个原pilot文件与固定SHA256一致，
输出目录必须不存在。只在forward的getter初始化之后插入
`if (warp_size != 32) std::abort();`，不改kernel、launch公式、算法/数据常量
或backward。这是带fail-stop限制的候选，不是native64适配、fallback，
也不证明全部原输入上的等价性；实际部署仍未授权。

源码checker先fresh保持query初值到guard，再检查同块紧邻minimum的plain
local/literal不等式与direct零实参noreturn失败调用。正常fallthrough推出
query值等于源码literal，而不是假设其值来自某张GPU的历史测量。
随后独立重新检查power来源、minimum、quotient历史/除法和整数域。

noreturn实际实现、源有效性、API输出与枚举转换等前提依旧保留。这里消除的
仅是此前额外的query数值域假设；它不是完整源程序或机器码证明。

## 候选准备与采集

```bash
PYTHONPATH=src:. python -m experiments.softmax_query_guard \
  --source artifacts/wb-softmax-hip-pilot-20260927-10 \
  --output artifacts/wb-hip-query-guard-candidate-20260930-01
PYTHONPATH=src python -m wavebridge.frontend.native_captures \
  artifacts/wb-hip-query-guard-candidate-20260930-01/pytorch-softmax-hip.hip.cpp \
  --compiler artifacts/toolchains/sdk-view-sx4rmd37/bin/hipcc \
  --plugin artifacts/toolchains/clang23-enum-20260930/libwavebridge_capture_plugin.so \
  --compiler-arg=-std=c++17 --compiler-arg=-O2 --compiler-arg=--offload-device-only \
  --compiler-arg=-DWB_COMPILED_COOP_WIDTH=32 \
  --compiler-arg=-I/home/husrcf/Code/ProtBind/wavebridge/artifacts/wb-hip-query-guard-candidate-20260930-01 \
  --timeout 120 --output artifacts/wb-hip-query-guard-candidate-20260930-01/native.json
```

新native SHA256：`df7d0b37e1d7ca16977f6d133285705d004a655e880b87b635148a373816e8b5`。
新kernel/header SHA256：`adaec400e1ce952d77e31044c53a76422ec818d750d9ddcdab2af33748c73ad5`。
候选manifest SHA256：`74f620ad61fb01563ea35ecc956f072cdd9f7ee27e37a21e24f4dcbba44bd2f0`。
主harness及compat头内容未改变。新AST指针ID不与旧AST混用。

## 新AST选点与外部协议

caller/main `0x2d777828`，input columns `0x2d777ee8`，输入守卫`0x2d77d188`，
调用`0x2d7f16f8`，callee `0x2d7f1410`，argument position=2。
exponent/power依次为`0x77692424b8a0`/`0x77692424b9a0`；query local
`0x77692424bac0`，新guard `0x77692424bc18`，minimum `0x77692424bda8`，
quotient `0x77692424bfb8`。getter/wrapper为`0x2d32ad88`/`0x2d329830`。

用新AST的fresh check_query_object/check_enum_binding重新绑定此前完全相同
语义的外部API输出与枚举保位协议，没有输入query-value-domain协议。
两个协议作为明确assumed输入保存于报告`conversion_contract_assumed`与
`output_contract_assumed`；它们没有因自动重新绑定而成为已验证协议。

可从报告仅提取协议/选点重新执行（不能复用check里的成功状态）：

```python
import json
from wavebridge.verification.field_snapshot import check_query_power_quotient
p = json.load(open('artifacts/wb-hip-query-guard-candidate-20260930-01/native.json'))['payload']
r = json.load(open('artifacts/wb-hip-source-guard-20260930-01/report.json'))
fresh = check_query_power_quotient(p, '0x77692424bac0', '0x77692424bda8',
    '0x77692424bfb8', r['selection'], r['conversion_contract_assumed'],
    r['output_contract_assumed'], query_guard_id='0x77692424bc18')
```

首次单guard检查得到unknown/ordinary_ast_identity_not_unique：真实std::abort
callee叶`0x2d766fa0`与模板共享，而CallExpr及decay唯一。修复仅支持这个
唯一调用child路径下全字段一致共享的终端引用叶，不做全局AST去重。
真实template回归另覆盖literal共享、literal/callee冲突及非bool If flags。

## 本地验收

完整1366项CPU测试141.901秒通过，无跳过，日志`/tmp/wb-source-guard-check.log`。
沿用Clang23 visibility/unary/using/enum与AOCC17 native插件组合；Clang23/17
各20项专项39.223/38.874秒通过，候选生成3项、demo/diff通过。
早期专项因未支持共享callee叶失败；支持修正后的专项与完整回归均重新执行。
Sol两轮只读复核无阻断。新采集status=collected、inputs_stable=true；
完成后再次核对三份历史输入SHA256，全部未变。

冻结实现SHA256：field_snapshot.py
`d1d63dbee474500c04cb15497cacb34fce99a15fcd42c26bc6c239b27ef07cba`；
normal_return_guard.py
`1a951b7686b92807ebf650ea48bda3ea94a28d1719180b908c82cababa55fb31`；
候选生成script
`5c89d5ed585d840fe1a81aeeea377f8b2683508d94d28ccc646f99f721bbdf2c`。

## 候选的实际组合结果

`artifacts/wb-hip-source-guard-20260930-01/report.json` SHA256：
`771f1a83bcc2c30b524f38a4245034bae47cd6558db99f5becb72285d0dae378`。
fresh query/guard/minimum/power/quotient均checked；source_guard_interval=[32,32]，
商区间[4,4]，division_safe_under_source_guard=true，
division_safe_under_domain_assumption=false。未提交query数值域外部协议。

source_program_checked/deployable仍false；新候选不是原始生产TU的无修改支持，
不是跨波宽优化或新GPU结果。下一步可连接后续launch字段与kernel/launch一致性；
不应因为此局部算术门槛通过就直接部署。
