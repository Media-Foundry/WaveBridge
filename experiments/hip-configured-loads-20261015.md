# Host配置派生坐标域到选定加载地址

日期2026-10-15，基线`a1011f8a0e5c2a5dfe760ec42fa911b4023d980d`。
本轮不改HIP源码、不运行GPU，输入仍是冻结的手工HIP守卫候选完整native AST。
它不是未经修改的上游生产TU；大型原始工件保存在本地ignored artifacts，
不称为随提交公开上传的完整复现包。

## 本轮解除的连接缺口

此前`check_fixed_guarded_loads`需要显式leaf域，不能将旧配置报告的数值
直接当成本次已证明的输入。新`check_guarded_coordinate_to_fixed_loads`
重新执行配置槽与字段保持、API轴域派生和getter检查，将本次派生的域传给
完整加载检查。只有同root/native envelope、kernel owner、coordinate、
双循环、ABI和调用协议完全对应，才给出组合checked。

普通内层入口的绑定逻辑提取成共用私有函数，旧API与语义不变。新增入口没有
接收旧成功报告或lane区间的接口；外部axis协议仍只指定精确API身份和角色，
不能填写数值域。配置变更导致域与源码标签宽度不一致时应保持unknown。

计数和指针快照仍使用[已冻结外部开发域](softmax-fixed-load-domain-protocol-20261015.json)：
n∈[0,128]于函数入口，row∈[0,4095]及stride∈[0,128]于offset求值。
这些不是本轮恢复出的launch实参域。stride和n保持不同符号；不把待证明的
值保持或等价关系换名塞入新协议。

组合仅支持选定赋值时的地址与目标对应：
`row_at_snapshot*stride_at_snapshot + outer*n + column`，以及
`elements[outer][inner]`。实际配置/coordinate API、硬件限制、外部调用
效果、无别名、正常执行等前提仍保留；跨lane共同count、实际线程参与、
完整load覆盖、分配/指针表示、输入内容和目标后续保持均未证明。
source/deploy保持false，不宣布WB-03或G2–G4完整通过。

## 重放与验证

完整HIP重放及全量验收均通过。全量1428项628.887秒，退出0、无跳过，
原始日志为check.log。以上为本地验收，未核验本提交远端CI，无新增GPU执行。
本地产物目录：`artifacts/wb-configured-loads-20261015-01/`。

重放退出0，695.167秒，`status=checked`，全部Python实现哈希在运行前后
一致。该时间覆盖完整host配置和加载检查，且同期有CPU回归运行；它不是
kernel性能或跨实现加速数据，也没有做热点归因。

| 项目 | 本次fresh结果 |
| --- | --- |
| block配置 | (32,4,1) |
| coordinate区间 | [0,31]，由本次配置派生，不由调用者填写 |
| 配置对象静态copy清单 | 22个，完整引用与复制保持按既有条件模型检查 |
| load / destination | `0x7769241ac7b8` / `0x7769241abd90` |
| 地址对应 | `row_at_snapshot*stride_at_snapshot + outer*n + column` |

fresh_configuration_composed、guarded_load_relation_checked、
entry_pointer_history_checked、count_domain_checked_under_external_interval为true；
API/runtime、硬件限制、实际参与、共同count、memory_load_coverage、
input_contents_preserved、source/deploy均为false。条件检查结论没有升级。

最终输入与实现绑定：

- native文件SHA256：`df7d0b37e1d7ca16977f6d133285705d004a655e880b87b635148a373816e8b5`。
- root SHA256：`037b5ce0092111b2f87f3d5a92468fef7481188457fd10020e04337cc59bd86d`。
- report.json SHA256：`b7320e27c207591cde771c93d0961177df7f7a3f986ab3d90b9d209dc3de290d`。
- replay.py SHA256：`7b5efe693a2b3f18bdc9c997a2a324c7b02e8a2f70f718e08fed19f7d2ed67ed`。
- block_configuration.py SHA256：`e153121c0288c306216d9b9adfd5f3320aa61a4153a5a3959d654d87eb053d0f`。
- test_configured_fixed_loads_clang.py SHA256：`1fbbe24644b045c46bcd56bd09b61ae3211400cc7e0d414526b7a5e0538a32d8`。
- configured_fixed_loads.cu SHA256：`d754ddb6f9924c1f541e65e40b7b69b32e6bdf512811569be99bc429750c7b76`。

来源选择报告及axis/domain协议的文件哈希完整保存在本次报告的
input_file_sha256，不把它们此前的status或数值结果当作本次检查前提。

已有配置专项16项202.096秒通过，日志`existing-config.log`。新增独立
native CUDA fixture及5项测试，无mock恢复器；覆盖配置宽度16而源码标签
宽度32、错误load下标、n/pointer写入、跨kernel坐标/循环、旧root、unused
协议、预算、身份冲突、手填leaf域入口，以及哈希/未建立标志。
最终新增专项5项99.222秒通过，记录在`tool-session.txt`：这是保留命令、
会话28771、退出0及累计原始返回文本的工具输出转存，不是shell原生日志。
最初5项91.924秒通过属于子代理观测；最终新增哈希和coordinate-owner断言
后的正式全量原生日志为`check.log`，不以初轮观察替代。
编译器为Clang17匹配native插件；不声称该专项已验证Clang23 native兼容性。
GPT-5.6 Sol只编辑两份新测试/fixture并只读复核生产组合入口，未发现阻断。
`make demo`和`git diff --check`通过，demo日志为`demo.log`。

全量实际命令沿用固定的compiler-matched配置：

```bash
WB_VISIBILITY_COMPILER=/home/husrcf/anaconda3/lib/python3.12/site-packages/_rocm_sdk_core/lib/llvm/bin/clang++ \
WB_UNARY_BUILTIN_PLUGIN=artifacts/toolchains/clang23-enum-20260930/libwavebridge_capture_plugin.so \
WB_UNARY_BUILTIN_COMPILER=/home/husrcf/anaconda3/lib/python3.12/site-packages/_rocm_sdk_core/lib/llvm/bin/clang++ \
WB_USING_SHADOW_COMPILER=/home/husrcf/anaconda3/lib/python3.12/site-packages/_rocm_sdk_core/lib/llvm/bin/clang++ \
WB_NATIVE_CAPTURE_PLUGIN=artifacts/toolchains/clang17-enum-20260930/libwavebridge_capture_plugin-final.so \
WB_NATIVE_CAPTURE_COMPILER=/opt/AMD/aocc-compiler-5.1.0/bin/clang++ \
WB_ENUM_CAPTURE_PLUGIN=artifacts/toolchains/clang23-enum-20260930/libwavebridge_capture_plugin.so \
WB_ENUM_CAPTURE_COMPILER=/home/husrcf/anaconda3/lib/python3.12/site-packages/_rocm_sdk_core/lib/llvm/bin/clang++ \
make check > artifacts/wb-configured-loads-20261015-01/check.log 2>&1
make demo > artifacts/wb-configured-loads-20261015-01/demo.log 2>&1
git diff --check
```

专项实际命令：

```bash
WB_NATIVE_CAPTURE_PLUGIN=artifacts/toolchains/clang17-enum-20260930/libwavebridge_capture_plugin-final.so WB_NATIVE_CAPTURE_COMPILER=/opt/AMD/aocc-compiler-5.1.0/bin/clang++ PYTHONPATH=src:tests python -m unittest tests.test_guarded_configuration_clang > artifacts/wb-configured-loads-20261015-01/existing-config.log 2>&1
WB_NATIVE_CAPTURE_PLUGIN=artifacts/toolchains/clang17-enum-20260930/libwavebridge_capture_plugin-final.so WB_NATIVE_CAPTURE_COMPILER=/opt/AMD/aocc-compiler-5.1.0/bin/clang++ PYTHONPATH=src:tests python -m unittest tests.test_configured_fixed_loads_clang
```

```bash
PYTHONPATH=src python artifacts/wb-configured-loads-20261015-01/replay.py > artifacts/wb-configured-loads-20261015-01/report.json 2> artifacts/wb-configured-loads-20261015-01/replay-stderr.log
```

本地replay.py仅从历史报告读取固定选点和外部契约，不读成功状态、leaf域、
配置字段结果或加载关系。它保存这些输入本身及来源文件哈希，全部Python
实现的启动/结束哈希，以及GPU未执行标记。核心可重放调用如下：

```python
import json
from wavebridge.verification.block_configuration import check_guarded_coordinate_to_fixed_loads
p = json.load(open('artifacts/wb-hip-query-guard-candidate-20260930-01/native.json'))['payload']
r = json.load(open('artifacts/wb-hip-source-guard-20260930-01/report.json'))
s = json.load(open('artifacts/wb-hip-guard-target-20260930-01/report.json'))['selection']
a = json.load(open('experiments/hip-guard-coordinate-api-20260930.json'))
d = json.load(open('experiments/softmax-fixed-load-domain-protocol-20261015.json'))
abi = {'int': {'bits': 32, 'signed': True},
       'unsigned int': {'bits': 32, 'signed': False},
       'unsigned long': {'bits': 64, 'signed': False}}
w = {'schema_version': 'builtin-leaf-effect-assumption/v1',
     'native_envelope_sha256': '058dd18d6928566e74bb9facd4cd797b2fc0185f108b1a281aa61e8ffac7ab48',
     'call_expression_id': '0x2b61f128', 'callee_declaration_id': '0x2b61ef60',
     'builtin_no_memory_write_assumed': True, 'valid_call_and_normal_return_assumed': True,
     'evidence_reference': 'UNVERIFIED development no-write/normal-return premise; not SDK or GPU proof'}
result = check_guarded_coordinate_to_fixed_loads(
    p, s, '0x77692424bac0', '0x77692424bda8', '0x77692424bfb8', '0x77692424c3c0',
    r['selection'], r['conversion_contract_assumed'], r['output_contract_assumed'], abi, a,
    '0x7769241ab3f0', '0x7769241acb28', '0x7769241acad0', {}, {'0x7769241aca08': w},
    d['input_parameter_id'], d['count_parameter_id'], d['count_interval'],
    pointer_binding=d['pointer_binding'], query_guard_id='0x77692424bc18',
    instantiated_function_id='0x2d7f1410')
print(json.dumps(result, indent=2))
```

下一项应处理逐行count与row来源、实际参与族及加载值对应，不能把本次条件
地址连接当成完整数值语义或自动适配成果。
