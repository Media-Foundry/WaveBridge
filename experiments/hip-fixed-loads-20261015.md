# 固定双循环的选定加载地址与入口指针历史

日期2026-10-15，基线`cb5f566f004d9db69ef50e725952a7d9191f4434`。
使用此前冻结的手工HIP守卫候选完整native AST，不修改真实源码，不运行GPU，
不声称处理未经修改的上游生产TU。大AST和原始日志仍是本地ignored产物，
本提交不构成可公开下载的完整复现包。

## 检查对象与边界

新增`column_coverage.check_fixed_guarded_loads`，从同一AST fresh检查：

1. 普通嵌套循环入口、完整递推、lane保持、仿射标签和严格小于guard。
2. count是同函数参数n，或其局部快照，或纯比较选择的`0/n`。
3. true arm只有`elements[i][it]=src[i*n+it*W]`；目标自动float[M][K]，
   n同函数int参数，src同函数const float*参数，逐signed算术检查范围。
4. 唯一直接`src += offset`及`offset = first_batch*stride+lane`，
   完整函数内src/offset/n显式用途闭合；两层报告精确绑定同root。

指针历史核心提取自已有输出检查，旧公共入口和保证边界保留；这不是新增
通用别名框架。所有间接/既有/保留别名不改受保护存储仍为外部前提，
不是由显式引用闭合自动证明。

源码中前缀使用stride，循环内使用n。得到的选定加载偏移为：

```text
first_batch_at_snapshot * stride_at_snapshot + lane + i*n + it*W
 = first_batch_at_snapshot * stride_at_snapshot + i*n + column
```

不把`i*n`替换成`i*stride`。新[固定开发域](softmax-fixed-load-domain-protocol-20261015.json)
将row∈[0,4095]、stride∈[0,128]、n∈[0,128]显式绑定当前native文件。
row/stride延续旧分析窗口的数值，但旧协议属于另一AST，不能直接复用其身份；
这里重新记录为未经验证的外部域，row/stride在offset求值时成立，n在函数入口
成立。count域保持依赖完整函数只读分类和已记录的noalias/effect前提。

仍未证明：真实row/getter/launch对应、逐行共同count、实际lane参与、合法分配、
指针表示、input内容保持、赋值后elements保持、归约/浮点结果、source/deploy。
只检查所选直接加载点，不排除别名或调用中的其他内存读取，不称为完整load
覆盖。leaf域和builtin效果仍显式假设；本轮没有fresh组合host配置链。

## 验收记录

本地产物目录`artifacts/wb-fixed-loads-20261015-01/`。

完整HIP重放93.230秒、退出0，`status=checked`，运行前后Python实现哈希一致：

| 项目 | 同次AST结果 |
| --- | --- |
| load / assignment | `0x7769241ac7b8` / `0x7769241ac7f0` |
| 自动目标数组 | `0x7769241abd90`，float[2][4] |
| guard count | 源码比较选择0或参数n |
| W / K / M | 32 / 4 / 2 |
| 前缀offset区间 | [0,524191]，依赖外部row/stride窗口 |
| 循环内相对下标区间 | [0,224]，尚未用guard缩紧的保守范围 |
| 同函数n的只读引用 | 10处 |

`guarded_load_relation_checked`、`entry_pointer_history_checked`及
`count_domain_checked_under_external_interval`为true；跨lane共同count、
实际线程参与、memory_load_coverage、input_contents_preserved、source/deploy
均为false。地址式建立不等于输入值或最终结果建立。

最终相关Clang专项30项：Clang17.0.6耗时79.172秒，Clang23.0.0git耗时
79.036秒，均退出0、无跳过，包括新增10项加载回归与既有标签/存储历史回归。
新增两项底层const-input/readonly核心回归随相关套件执行。初轮新增8项
45.446秒通过，后续补齐count隐藏槽位/重复身份及错误pointer binding后为10项。
合成CPU哨兵值测试实际编译执行源程序，遍历7个n值、32个模拟lane及两行，
故意使用stride=117且n可不同，以检验不混淆两个量；错步长版本出现预期
不一致。它不是GPU或浮点精度实验。所有源码回归不mock恢复器。

GPT-5.6 Sol完成有界核心提取及独立只读复核，未发现阻断；建议的组合负例
已补入。`make demo`、`git diff --check`通过；全量1423项518.941秒、退出0、
无跳过。日志`check.log`及`demo.log`；全部为本地验收，未核验本提交远端CI。
本轮新增回归和完整HIP重放没有失败后放宽实现的过程，初轮8项通过记录保留。

实际命令：

```bash
PYTHONPATH=src python artifacts/wb-fixed-loads-20261015-01/replay.py > artifacts/wb-fixed-loads-20261015-01/report-first.json
PYTHONPATH=src python -m unittest tests.test_fixed_guarded_loads_clang tests.test_fixed_guarded_labels_clang tests.test_guarded_store_pointer_history_clang tests.test_guarded_stores_clang > artifacts/wb-fixed-loads-20261015-01/clang17.log 2>&1
PATH=/home/husrcf/anaconda3/lib/python3.12/site-packages/_rocm_sdk_core/lib/llvm/bin:$PATH PYTHONPATH=src python -m unittest tests.test_fixed_guarded_loads_clang tests.test_fixed_guarded_labels_clang tests.test_guarded_store_pointer_history_clang tests.test_guarded_stores_clang > artifacts/wb-fixed-loads-20261015-01/clang23.log 2>&1
```

全量命令沿用compiler-matched插件配置，不宣称完整Clang23 native capture兼容：

```bash
WB_VISIBILITY_COMPILER=/home/husrcf/anaconda3/lib/python3.12/site-packages/_rocm_sdk_core/lib/llvm/bin/clang++ \
WB_UNARY_BUILTIN_PLUGIN=artifacts/toolchains/clang23-enum-20260930/libwavebridge_capture_plugin.so \
WB_UNARY_BUILTIN_COMPILER=/home/husrcf/anaconda3/lib/python3.12/site-packages/_rocm_sdk_core/lib/llvm/bin/clang++ \
WB_USING_SHADOW_COMPILER=/home/husrcf/anaconda3/lib/python3.12/site-packages/_rocm_sdk_core/lib/llvm/bin/clang++ \
WB_NATIVE_CAPTURE_PLUGIN=artifacts/toolchains/clang17-enum-20260930/libwavebridge_capture_plugin-final.so \
WB_NATIVE_CAPTURE_COMPILER=/opt/AMD/aocc-compiler-5.1.0/bin/clang++ \
WB_ENUM_CAPTURE_PLUGIN=artifacts/toolchains/clang23-enum-20260930/libwavebridge_capture_plugin.so \
WB_ENUM_CAPTURE_COMPILER=/home/husrcf/anaconda3/lib/python3.12/site-packages/_rocm_sdk_core/lib/llvm/bin/clang++ \
make check > artifacts/wb-fixed-loads-20261015-01/check.log 2>&1
make demo > artifacts/wb-fixed-loads-20261015-01/demo.log 2>&1
git diff --check
```

哈希绑定：

- native文件SHA256：`df7d0b37e1d7ca16977f6d133285705d004a655e880b87b635148a373816e8b5`。
- AST root SHA256：`037b5ce0092111b2f87f3d5a92468fef7481188457fd10020e04337cc59bd86d`。
- `report-first.json` SHA256：`81c0892ff713fe4fff98e9b59f40a2bd117df8f9c9645287219325a9613d355a`。
- replay.py SHA256：`c4459289fb6fb4c5a3dd13a7971196225eb8fdfc736d14b61c3b0dc632c876c4`。
- domain protocol SHA256：`88b272c7a5f93dc42c68ff092e47bbb8c3c3965daa73901a9d1519c53aebc919`。
- column_coverage.py SHA256：`dfe862574bfd8998970c757b31436bc11ee2a4f5e962bea6ec4df0b696f98e7b`。
- guarded_stores.py SHA256：`a1b80cdb146946178de7d9134370bbdb0eb7653fbe55602e7e2246f53cb87354`。
- test_fixed_guarded_loads_clang.py SHA256：`9aa67515538d0d719c87ddea4482142753860b7c4c51a42d493be6a57493d718`。
- test_guarded_store_pointer_history_clang.py SHA256：`2b34ad8cd59404f1623ff565b2a0a8a03d54e2741811de23df72235176c42096`。

实际核心重放调用（前置leaf/abi/work与[标签实录](hip-fixed-labels-20261015.md)
的完整代码相同；p为完整native文件payload，不裁剪AST）：

```python
import json
from wavebridge.verification.column_coverage import check_fixed_guarded_loads
with open('experiments/softmax-fixed-load-domain-protocol-20261015.json') as f:
    domain = json.load(f)
result = check_fixed_guarded_loads(p, '0x7769241ab3f0', '0x7769241acb28',
    '0x7769241acad0', leaf, abi, {}, {'0x7769241aca08': work},
    domain['input_parameter_id'], domain['count_parameter_id'], domain['count_interval'],
    pointer_binding=domain['pointer_binding'])
```

本地replay.py额外记录全部Python实现哈希、运行前后不变检查、原始文件哈希、
外部域、脚本哈希和计时。它不调用GPU，不采集新的HIP编译工件。

下一项：将本次选定加载关系与host配置重新组合，继续解除row/count共同性、
实际参与和加载值对应义务；不能直接拼接几份历史成功报告声明WB-03完整通过。
