# 固定双循环中的源码列标签与条件覆盖

日期2026-10-15，基线`7cefc5a4212133eaca853121e1aa4947645e0e39`。
本轮未修改HIP源码、未运行GPU；使用此前冻结的守卫候选完整native AST，
不称为未经修改的上游生产TU。大AST和原始报告仍在本地ignored artifacts，
没有随代码上传为完整复现包。

## 实现与精确边界

`column_coverage.check_fixed_guarded_labels`重新检查普通嵌套入口，再匹配真实
内层的标签声明、typed仿射表达式、`< count`和count存储保持。没有按函数名
或变量名填关系模板，没有读人工关系oracle。逐个算术节点检查signed范围，
常量从源码重新求值；未识别表达式、隐藏语义槽位或身份冲突保持unknown。
支持子集和API见[检查器说明](../compiler/verification/README.md)。

形式结论：对每个固定outer iteration／逻辑行，在恰有一个实例取每个
lane∈[0,W)且完整正常执行it∈[0,K)的前提下，`c=lane+it*W`将形式实例与
[0,WK)一一对应；进一步要求同一行各实例有共同n∈[0,WK]，`c<n`筛出
恰好一次的[0,n)。唯一表示是`lane=c%W,it=c//W`。

这是源码标签与形式索引族的对应，不是实际内存读取覆盖。实际线程参与、
count入口域及跨lane相同性、指针偏移/历史、分配、加载值和后续归约均未证明。
源有效性、ABI、noalias、外部调用无写入及正常返回仍是前提。
其中count的间接写入（包括既有/保留别名）不别名该存储单独列为前提，
不能由针对lane或induction的已有noalias前提代替。
本入口使用显式leaf域；未重新跑host配置链，不能直接拼接此前配置报告。

## 真实结果

最终重放退出0，检查耗时82.051秒，`status=checked`：

| 项目 | 同次AST结果 |
| --- | --- |
| coordinate声明 | `0x7769241ab3f0` |
| outer / inner循环 | `0x7769241acb28` / `0x7769241acad0` |
| label / count声明 | `0x7769241ac278` / `0x7769241abf78` |
| guard / inner induction | `0x7769241aca80` / `0x7769241ac110` |
| 源码系数 / 迭代数 | W=32，K=4 |
| 标签区间 / 支持的共同count域 | [0,127] / [0,128] |

源码常量`0x7769241aa6d8`重新求值得32，保留完整依赖与Clang模板替换记录。
成功报告的`formal_label_coverage_checked=true`不改变以下false标记：
actual_thread_participation_checked、guard_count_entry_domain_checked、
memory_load_coverage_checked、pointer_history_checked、source_program_checked、
deployable；重放元数据也明确`fresh_configuration_composed=false`和`GPU_executed=false`。

## 输入与工件绑定

工件目录：`artifacts/wb-fixed-labels-20261015-01/`。

- native文件：`artifacts/wb-hip-query-guard-candidate-20260930-01/native.json`。
- native SHA256：`df7d0b37e1d7ca16977f6d133285705d004a655e880b87b635148a373816e8b5`。
- AST root SHA256：`037b5ce0092111b2f87f3d5a92468fef7481188457fd10020e04337cc59bd86d`。
- 最终`report-final.json` SHA256：`437aa32da9c4d544341f29deffdb60f36db480ca31dacaf681e4c9aba7094699`。
- `column_coverage.py` SHA256：`adfb8831ef5bf1b9aea07864eb92793e1572a13eba838fde4f3c6571653d404b`。
- `test_fixed_guarded_labels_clang.py` SHA256：`317781eae012ca4b13b57b93be1736c094b0714dad760358b5219fbc0a57f85e`。

实际命令：

```bash
PYTHONPATH=src python artifacts/wb-fixed-labels-20261015-01/replay.py > artifacts/wb-fixed-labels-20261015-01/report-final.json 2> artifacts/wb-fixed-labels-20261015-01/replay-final-stderr.log
```

该本地脚本的SHA256为`9f1a99608f77f57f8c0019377c3d531b3d84e94f9d9644c6051378f339b2aceb`。
它记录全部`src/wavebridge/*.py`递归文件哈希，并核实运行前后未变。可在仓库根
使用以下完整核心调用重新产生checker结果（不含原脚本的计时与文件清单外壳）：

```python
import json
from wavebridge.verification.column_coverage import check_fixed_guarded_labels
with open('artifacts/wb-hip-query-guard-candidate-20260930-01/native.json') as f:
    p = json.load(f)['payload']
leaf = {'schema_version': 'getter-leaf-domain/v1', 'declaration_id': '0x2d313928',
        'return_type': {'qualType': 'unsigned long'}, 'arguments': [0], 'lower': 0, 'upper': 31}
abi = {'int': {'bits': 32, 'signed': True},
       'unsigned int': {'bits': 32, 'signed': False},
       'unsigned long': {'bits': 64, 'signed': False}}
work = {'schema_version': 'builtin-leaf-effect-assumption/v1',
        'native_envelope_sha256': '058dd18d6928566e74bb9facd4cd797b2fc0185f108b1a281aa61e8ffac7ab48',
        'call_expression_id': '0x2b61f128', 'callee_declaration_id': '0x2b61ef60',
        'builtin_no_memory_write_assumed': True, 'valid_call_and_normal_return_assumed': True,
        'evidence_reference': 'UNVERIFIED development no-write/normal-return premise; not SDK or GPU proof'}
print(json.dumps(check_fixed_guarded_labels(p, '0x7769241ab3f0', '0x7769241acb28',
    '0x7769241acad0', leaf, abi, {}, {'0x7769241aca08': work}), indent=2))
```

leaf域来自此前配置结果的数值，但在本次调用中只是显式外部假设，不是本次
配置推导结论。builtin协议同样未经SDK效果证明；实际调用结构被fresh检查。

## 验收与失败记录

新增真实Clang专项8项，无mock恢复器；最终Clang17.0.6运行6.594秒、Clang23.0.0git
运行6.174秒，均退出0、无跳过。日志`clang17-final.log`、`clang23-final.log`。
覆盖正确/重排表达式、错误步长/偏移/guard、count直接和引用别名改写、中间
溢出、错循环、预算、输入不变，以及隐藏/畸形semantic slot。
另有有界公式枚举与编译执行的CPU计数对照，后者只模拟一个逻辑行的32个实例。
故意错误的内存地址仍可具有正确标签，但memory/source/deploy保证保持false。

CPU计数测试首版错误沿用了`else output[it]=0`，会擦除此前计数，导致1项失败；
`unit-final.log`保留这份失败。修复仅将合成计数fixture的else改为空，普通正负
源码fixture仍保留原else，未放宽checker或修改真实HIP。修正后7项通过见
`unit-corrected.log`；最后加入scalar/guard隐藏槽位回归后为上述8项。
GPT-5.6 Sol只读复核无阻断，要求的逐行common-n和全scalar slot拒绝已落实。
最后核对补充了独立的count间接别名前提及报告断言，因此重新进行最终验收。
补充前的8项日志`unit-hardened.log`、`clang23.log`以及首轮全量1411项
464.359秒的`check.log`均保留；初次重放`report.json`耗时82.751秒，SHA256
`00348254fafdff93c093da434f93b89fa397cfa32b7d47233886aa8f84a27f6a`，不替代最终报告。

全量验收使用原有工具链配置：native capture为Clang17匹配插件，其余指定
专项为Clang23；不宣称完整Clang23 capture兼容。实际命令：

```bash
WB_VISIBILITY_COMPILER=/home/husrcf/anaconda3/lib/python3.12/site-packages/_rocm_sdk_core/lib/llvm/bin/clang++ \
WB_UNARY_BUILTIN_PLUGIN=artifacts/toolchains/clang23-enum-20260930/libwavebridge_capture_plugin.so \
WB_UNARY_BUILTIN_COMPILER=/home/husrcf/anaconda3/lib/python3.12/site-packages/_rocm_sdk_core/lib/llvm/bin/clang++ \
WB_USING_SHADOW_COMPILER=/home/husrcf/anaconda3/lib/python3.12/site-packages/_rocm_sdk_core/lib/llvm/bin/clang++ \
WB_NATIVE_CAPTURE_PLUGIN=artifacts/toolchains/clang17-enum-20260930/libwavebridge_capture_plugin-final.so \
WB_NATIVE_CAPTURE_COMPILER=/opt/AMD/aocc-compiler-5.1.0/bin/clang++ \
WB_ENUM_CAPTURE_PLUGIN=artifacts/toolchains/clang23-enum-20260930/libwavebridge_capture_plugin.so \
WB_ENUM_CAPTURE_COMPILER=/home/husrcf/anaconda3/lib/python3.12/site-packages/_rocm_sdk_core/lib/llvm/bin/clang++ \
make check > artifacts/wb-fixed-labels-20261015-01/check-final.log 2>&1
```

最终`make check`共1411项459.779秒，退出0、无跳过，日志`check-final.log`。
`make demo`（`demo-final.log`）及`git diff --check`通过；最终源码/测试/报告
哈希再次核对一致。以上为本地验收，不代称远端CI通过，无新GPU或实际kernel数值结果。

下一项应检查共同count域、参与实例和实际load地址与标签的对应，并与配置链
fresh组合；不把本次形式覆盖当作整核或WB-03完整验收。
