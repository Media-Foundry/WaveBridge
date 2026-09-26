# 从源码建立 closure 来源

- 日期2026-09-26，分支wb03-source-ast，基线0c0a8ff；中文、直接commit/push。
- 已核实0c0a8ff、b562c42、f707919的CI均success（36231021315、36230649051、36230240656）。
- 在既有capture_source_check中增加严格v2协议，不另建checker模块。
  v2删除closure_instances_from_recorded_lambdas_assumed，若仍提供该键则unknown。
  v1保持原条件身份语义，不静默迁移既有证据。
- v2对reference capture chain逐层fresh执行lambda_invocation，核对lambda、
  closure、root hash及copy唯一语义祖先上的call→lambda→body链。
  捕获初始化器不会算作所属lambda body；不借用外部通过子报告。
- source_initialized_alive、same-activation、source-valid前提仍严格保留。
  不推导可达性、次数、历史保持或GPU语义；copy被求值是来源结论的条件。
- 真实正例：直接/嵌套立即调用、另一lambda捕获初始化器中的立即调用。
  负例：具名、传出、返回、外层具名内层立即调用。返回悬垂capture例子只编译
  检查，不执行。顶层object_use_closure两条真实路径也用v2跑通。
- GPT-5.6 Sol只读复查未发现阻断问题。另修复非法schema为list/dict时的
  类型边界，采用精确版本比较，不对不可信值执行set membership。

## 验证记录

匹配插件：artifacts/capture-plugin-cleanups-gYQ3gz/libwavebridge_capture_plugin.so。
编译器：/opt/AMD/aocc-compiler-5.1.0/bin/clang++。
12项capture定向测试通过；最终全仓验收句柄48737（make check及demo）退出0：
665项CPU及demo通过；Clang专项句柄72572退出0，189项通过。
日志位于artifacts/wb-capture-origin-0fR6bN/final-*.log。
早一轮tests.log/clang.log与末次类型边界编辑并行，不作为最终代码验收证据。

## 完整TU重放结果

命令：WAVEBRIDGE_JSON_HASH_MODE=one-shot PYTHONPATH=src python3 artifacts/wb-capture-origin-0fR6bN/check.py。
exec session79110已退出0，PID214499已结束。日志run.log，终态report.json。
固定原生TU SHA256 f80432e744686fdc1390308073a3cd7e1b1d1ba5afd065198dcc292ab21ee9ee。
从旧工件仅读取外部协议，明确迁移为v2：删origin布尔，其他前提不变。
重新运行全部检查并核对77个实现文件前后哈希；任务存活时不改src，不因超时重启。
本次主引用闭合、source_order及source_reference_use_effects均checked。
三个capture-source-check/v2结果及各自closure_origin均checked，每条路径
fresh检查两层立即lambda。最终premises只保留alive、same-activation、valid，
不含closure来源布尔。耗时668.9996035850054秒，77个实现文件前后哈希稳定，
并通过sha256sum --check确认当前源码匹配，源码冻结已解除。
报告SHA256：b37dc9c07131293f9a50ee73c85cd3ea4d344dc5cbe2caca62eec88c6f7fa894。
未运行GPU；不是把既有v1成功升级，而是同一固定TU上的fresh v2重放。

## 等待期间的保证边界回归

ed1f610的CI 36231319359和13bbbd4的CI 36231471234已success。
仅修改测试/文档，未改冻结的src。
新增immediate_changed_source：原始source.x=3，立即lambda写为99后copy。
同份真实AST的v2身份/来源checked，object_use_closure因显式写入unknown；
CPU执行复制得到99（返回悬垂capture的另一个fixture函数从未执行）。
此有限CPU反例证明来源关系不能替代历史保持，不是GPU实验。
13项capture定向、666项CPU、190项Clang与demo退出0；新日志为同目录
boundary-tests.log、boundary-clang.log、boundary-demo.log。

Sol只读分析提出：v2的精确ordinary FunctionDecl绑定、自动source声明、完整
reference capture链和连续原始receiver调用路径，可能已足以从源码解除
same-activation前提。后续需主代理核实自动局部作用域及coroutine边界，补递归
立即调用正例/跨调用具名closure负例；不得直接修改已发布v2协议含义或将该
审阅意见当作已实现保证。alive/source-valid仍保留。本次终态已核验，下一项
实现可在明确版本兼容与动态activation定义后开始。
