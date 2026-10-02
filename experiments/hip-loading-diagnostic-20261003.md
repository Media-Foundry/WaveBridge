# 真实HIP首个加载循环：恢复缺口定位

基线8aecf97，2026-10-03。未修改候选或checker，没有GPU执行。
此次只做原始AST上的支持性诊断，不签发配置→循环体或列覆盖保证。

## 已核实结果

冻结native文件SHA256沿用
`df7d0b37e1d7ca16977f6d133285705d004a655e880b87b635148a373816e8b5`。
kernel `0x7769241d57f0`；完整root未裁剪、未移除调用、未插入break。

| 对象 | 精确ID | 原始循环头 | 默认递推恢复 |
| --- | --- | --- | --- |
| 外层加载循环 | 0x7769241acb28 | start=0，bound=2，step=1，observed | unknown：call_in_body |
| 内层加载循环 | 0x7769241acad0 | start=0，bound=4，step=1，observed | unknown：call_in_body |

两个bound分别来自源码常量声明 `0x7769241aaa58`、`0x7769241aa8c0`，
经过observe_header的常量重检，不是手填模型。observed不等于完整递推checked。
共同未知点是调用 `0x7769241aca08`，头文件字节offset 5182–5219，
对应填充分支的 `std::numeric_limits<acc_t>::infinity()`。
这里没有给它提供外部效果协议，也没有因函数名字看似纯函数就放行。

旧loop_exit_guards.check_header_connection在两层均unknown，reason为
prefix_values_not_checked，子原因exit_partition_not_checked。该入口面向
显式break分区，不能把它作为当前普通固定次数for的必要语义条件。

## 下一项实现边界

优先复用column_loops已有的一层固定次数嵌套恢复和builtin wrapper效果检查。
需要精确绑定上述调用的wrapper/leaf，保留任何显式外部效果前提；不能仅按
infinity名称放行。随后保护local_idx跨整个外层与内层的存储，而不只保护
各自induction；再把local_idx + it * WARP_SIZE与条件加载及输出归属连接。
循环头常量或数学上32×4=128均不能替代源码列覆盖、指针合法性或线程参与证据。

## 实际命令与工件

本地脚本 `/tmp/wb-loading-diagnostic.py` 使用完整原始AST，依次调用
observe_header、内部_recover_loop（仅诊断）和check_header_connection。
调用方式：

```bash
PYTHONPATH=src python /tmp/wb-loading-diagnostic.py > artifacts/wb-hip-loading-diagnostic-20261003-01/report.json
```

两层循环通过所选外层原AST子树中的ForStmt枚举，未使用函数名模式选点。
报告保留原始header、默认恢复、失败原因、调用ID和源码range。进程退出0
仅表示诊断完成；两项递推均unknown，source_program_checked/deployable=false。
大native及原始报告均为本地ignored工件，不声称完整复现包已经上传。

报告SHA256：`eedcc3a8c03e32dff4c17daf657b6df03f57e00f3df4fd4935c26821cb830ad0`。
检查实现column_loops.py SHA256：
`7744c0a61407d7c14a41ba225d6b2aa0ffbc5f398cca8c5cf4930f72c019c327`；
loop_exit_guards.py SHA256：
`db5a21ec216568e852eeafe15b0b93c1788cb9fdbd2af75df5ae93bb0ac7d3c7`。

可重新执行以下最小诊断以核对同一结论（输出为摘要，不与原报告逐字相同）：

```bash
PYTHONPATH=src python - <<'PY'
import json, hashlib
from wavebridge.frontend.clang_ast import _walk
from wavebridge.analysis.column_loops import observe_header, _recover_loop
from wavebridge.verification.loop_exit_guards import check_header_connection
with open('artifacts/wb-hip-query-guard-candidate-20260930-01/native.json', 'rb') as f:
    raw = f.read()
assert hashlib.sha256(raw).hexdigest() == 'df7d0b37e1d7ca16977f6d133285705d004a655e880b87b635148a373816e8b5'
root = json.loads(raw)['payload']['ast']
del raw
kernel, = [n for n in _walk(root) if n.get('id') == '0x7769241d57f0']
outer, = [n for n in _walk(kernel) if n.get('id') == '0x7769241acb28']
for loop in _walk(outer):
    if loop.get('kind') != 'ForStmt':
        continue
    h = observe_header(root, loop['id'], 32)
    r = _recover_loop(root, loop, 32)
    g = check_header_connection(root, loop['id'], 32)
    print(json.dumps({'id': loop['id'], 'header': h, 'recurrence': r,
                      'guarded_status': g['status'], 'guarded_reason': g['reason']}))
PY
```
