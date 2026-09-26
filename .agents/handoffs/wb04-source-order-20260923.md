# 源声明与复制的结构顺序

- 日期：2026-09-23，2026-09-26续验；分支 `wb03-source-ast`；基线 `a07784d`。
- 上轮为已验证进展，本轮核验其CI `35770508173` success。
- 中文、直接commit/push，不建PR，不合并master。

## 实现及范围

修改已有object_use_closure，不新增getter模块。语义walk记录每个节点真实
祖先，复用本次fresh lambda_invocation结果；copy必须在source相同CompoundStmt
的后续直接child之内，且每层LambdaExpr之前确有其fresh call ID，copy在该
lambda body中。使用节点身份与child次序，不比较源码line/offset。
子报告 `source-copy-structural-order/v1` 记录声明/外围语句ID与索引、copy ID和
outer→inner立即调用链。重复closure record仍跳过，已有冲突检查不放宽。

固定vLLM dispatch_utils.h使用AT_DISPATCH_SWITCH，因此没有停留在只支持无
switch测试的替代路径。新增受限switch：完整位于source scope后续child，
唯一semantic ID，Case/Default/Break归属该switch且不跨LambdaExpr。
goto/label/一般loop/try/coroutine/未知Stmt/GNU statement expression等unknown。
真实ForStmt的空placeholder若先被原引用闭合层拒绝，继续拒绝，不为新测试放行。

Sol只读复查发现并修复孤立break和switch ID不唯一边界。报告仅签结构顺序，
source_lifetime、source_value_preservation、执行次数/可达性、外部非局部控制
效果仍not_established；主status可以checked而source_order unknown。

## 本地验收

```bash
export WB_NATIVE_CAPTURE_PLUGIN="$PWD/artifacts/capture-plugin-cleanups-gYQ3gz/libwavebridge_capture_plugin.so"
export WB_NATIVE_CAPTURE_COMPILER=/opt/AMD/aocc-compiler-5.1.0/bin/clang++
make check
make demo
PYTHONPATH=src python3 -m unittest discover -s tests -p '*clang*.py'
```

654项CPU、178项Clang专项和demo均退出0，插件测试实际执行；日志位于
`artifacts/wb-source-order-f6DfJD/{final-tests,clang,final-demo}.log`。
真实普通、嵌套作用域、立即lambda、三分支与switch正例；真实loop/goto/try及
source前switch未知。合成语句重排但offset不改、未知语句、缺switch ID、孤立
break均不能建立顺序；合成变体不作为可编译运行反例。

## 完整TU任务

命令：`WAVEBRIDGE_JSON_HASH_MODE=one-shot PYTHONPATH=src python3 artifacts/wb-source-order-f6DfJD/check.py`。
原exec session85108，日志 `run.log`，终态报告 `report.json`。原样使用固定native
TU，重用旧实验记录中的显式ABI、输入域和capture协议作为外部条件，不读取或
传递旧成功子报告；本次check内部fresh运行全部分析。运行期间冻结全部Python
实现，结束时核对哈希。未运行GPU，不因进程运行或超时观察而当作通过。

9月26日核验原报告：主引用闭合checked，但source_order为unknown，原因
source_order_control_flow_unsupported；耗时431.7890107239946秒，77个实现
哈希稳定。原session已不可取回退出码，不补写exit0。报告SHA256：
`6abb84be952b07892bd72cf4870d2bd6b5829e5fadf39c62c01db3d2acee20b3`。
诊断同一函数语义body得到7个DoStmt；固定Torch头文件含while(false/0)包装。

## 受限do包装续验

仅接受CompoundStmt body及无child的bool false，或精确IntegralToBoolean
转换的无child int字面量0。要求包装具有唯一semantic ID、完整位于source
scope后续child；Break绑定最近的受支持switch/do，Case/Default不得越过do，
Lambda隔离控制转移。动态/true/continue、隐藏条件子表达式、Duff式case跨入
均unknown。不依据宏名或任意常量折叠放行。Sol只读复查未发现阻断问题。

最终定向19项、全仓657项CPU、181项Clang专项及demo退出0；匹配原生插件
启用，日志在 `artifacts/wb-source-order-do-a9Svlt/` 的
`targeted.log`、`tests.log`、`clang.log`、`demo.log`。

新完整TU命令：
`WAVEBRIDGE_JSON_HASH_MODE=one-shot PYTHONPATH=src python3 artifacts/wb-source-order-do-a9Svlt/check.py`。
exec session9477仍在执行；只读旧报告的外部ABI/输入域/capture协议，重新运行
全部子检查，不消费旧成功结论。源实现冻结；完成后核对77个文件哈希。
当前没有终态结论，不能记为完整TU顺序通过。旧unknown工件不覆盖。

## 下一步

结构顺序是历史组合的输入而非同义替代；下一阶段仍需独立检查对象生命周期、
引用别名范围及C++方言/对象模型边界，不用no_alias或value_preserved布尔假设
直接换取历史成功。未达到源码→自动改写→GPU部署的完整门槛。
