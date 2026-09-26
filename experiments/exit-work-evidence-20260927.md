# 退出循环工作分支的依赖存储保持性

2026-09-27，wb03-source-ast，基线e983ebf。无GPU、无生产AST重采。

```bash
PYTHONPATH=src python3 -m experiments.softmax_exit_guards \
  --native artifacts/wb-column-builtins-twz82w/native.json \
  --recovery artifacts/wb-loop-calls-SIr4BJ/all-calls.json \
  --work-preservation --int-bits 32 \
  --output artifacts/wb-exit-work-lAU27h/replay.json
```

checker重新检查header/prefix/guard连接，保护induction、header start/bound
和prefix/guard外部读取对象，逐项检查work中的所有分支和存储目标。driver
仅选择原循环内的旧协议身份及显式未验证前提；完整call检查重新执行。

成功不等于全部work无写：输出写入可接受，但依赖明确的无别名、源有效和无
异步干扰前提。callee无写协议不能掩盖实参副作用或work的其他修改。未知
调用、嵌套loop和未消费协议不放行；局部成功不能提升unknown父报告。

固定回放inputs_unchanged=true，输出SHA256：
`d5cdc4fe5992741cded425ef4cfb1ce0224336ae3400faf75a4dbf23a59ab313`。
内层work checked；保护element_count、WARP_SIZE、WARP_ITERATIONS、local_idx和
it的精确声明，调用0x19550c18 fresh checked，unused为空。该调用的外部builtin
无写/正常返回仍为未验证前提。外层work unknown：offset8324–8339的std::log
调用尚无效果证据，尚未抵达嵌套loop的检查点。不能据此声称嵌套work已通过。

当前检查遍历全部条件分支，不利用is_log_softmax模板条件裁掉该log分支；
如要利用静态分支事实，必须从同次AST独立核验条件及所选分支，不能凭案例
配置或函数名忽略调用。历史6/8恢复不升级，整数域/溢出与完整覆盖仍未证明。

完整1048项测试通过（70.672秒，匹配native插件，无跳过），demo/diff通过。
GPT-5.6 Sol新增4项真实Clang回归并复核，特别覆盖header连接成功但work修改
依赖的负例。远端CI未核验，不产生整核、跨波宽、GPU或holdout结论。
