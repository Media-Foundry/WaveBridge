# 复制目标对象与析构门控

- 日期2026-09-26，分支wb03-source-ast，基线0e2df04；中文回复，用户授权直接提交推送当前分支，不开PR。
- src/wavebridge/record_copy_check.py复用fresh结构解析，新增object_boundary子报告；不新增外部noalias或value-preserved布尔。
- 支持complete/prvalue复制直接初始化单独块局部普通自动VarDecl，或既有精确by-value参数路径。精确绑定owner/声明/类型/作用域，排除source==target。
- record析构需正面的trivial布尔证据，无nonTrivial/userDeclared冲突；现存声明须唯一implicit/defaulted且无未支持属性/效果。缺失、冲突、显式用户defaulted、非trivial均unknown。
- 成功仅建立有效复制求值下目标与求值源实参的抽象对象边界，以及这个record的析构分类。不是原始捕获source身份、物理ABI地址、外围完整表达式cleanup、callee效果、source lifetime或历史保持保证。
- parent structure/value状态不自动随子报告升级；alive协议未删除。compiler/verification说明、ADR0003和docs/status.md同步。
- GPT-5.6 Sol负责测试与最终只读审查；未发现真实Clang输入下的阻断问题。元数据synthetic负例不称为真实源码执行。

## 验证

主代理启用匹配原生插件与Clang17：
WB_NATIVE_CAPTURE_PLUGIN=$PWD/artifacts/capture-plugin-cleanups-gYQ3gz/libwavebridge_capture_plugin.so
WB_NATIVE_CAPTURE_COMPILER=/opt/AMD/aocc-compiler-5.1.0/bin/clang++

- make check：678项，退出0；artifacts/wb-object-boundary-caJQpc/tests.log。
- PYTHONPATH=src python3 -m unittest discover -s tests -p '*clang*.py'：202项，退出0；同目录clang.log。
- make demo：退出0，同目录demo.log。
- 子代理系统Clang与ROCm Clang23各28项record-copy专项通过。
- 正例：普通自动对象、manual/implicit copy、精确按值参数。负例：placement-new、ref/static/TLS/self-init、非trivial/用户default析构；合成缺失/非bool/冲突dtor、owner冲突、target属性、非complete、隐式析构invalid/body/属性。
- git diff --check通过。

## 固定生产TU三点重放

命令：PYTHONPATH=src WAVEBRIDGE_JSON_HASH_MODE=one-shot python3 artifacts/wb-object-boundary-caJQpc/check.py。
会话42506退出0，耗时154.8544424510037秒。输入完整AST文件SHA256：
f80432e744686fdc1390308073a3cd7e1b1d1ba5afd065198dcc292ab21ee9ee。
只从旧工件读取外部整数ABI，不复用任何旧成功报告。
复制点0x37382628/0x37388288/0x3738de68：结构及object_boundary均checked；
target为exact_by_value_parameter 0x2135ca90，源声明0x373701f0。
record 0x20c73518，implicit trivial析构声明0x20d18870。
报告SHA256：4984286a8ae5d54a6bab291e36d1ac72068ae32139a477b0f76ccbe6daf6a2cd。
77个实现哈希前后一致，当前sha256sum --check --status退出0；源码冻结解除。

未运行GPU，未重跑整套object_use_closure/v3生产组合；该新子报告尚未被生命周期组合消费。
不存在本轮性能或整体等价结论。下一步：在同次native元数据中核验所需外围cleanup，
再显式组合独立结构、对象边界、来源与顺序；不能只看parent status，也不应提前删除alive。
本交接随已验收实现直接提交推送；不合并master、不创建PR。
