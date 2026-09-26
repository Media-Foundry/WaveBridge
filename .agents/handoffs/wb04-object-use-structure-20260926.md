# 独立显式引用结构组合

- 2026-09-26，wb03-source-ast，基线fdf3681；中文回复，直接commit/push，不开PR。
- 新入口verification.object_use_closure.inspect_structure，schema object-explicit-use-structure/v1。参数只有payload/source ID/ABI/初始化选择域/预算，不接收capture协议。
- direct copy fresh record_copy.inspect_effects；captured copy fresh capture_source.inspect_structure。共享私有_semantic_inventory与旧check的严格遍历/引用分类，不调用条件copy/identity检查，不伪造alive协议。
- copy_structures/capture_structures保存结构子报告，lambda调用绑定来自本次fresh捕获报告，按精确lambda ID去重并核对重复报告一致。_reference_use_effects的structural=True消费copy_structure；默认旧行为不变。
- conditional_initialization原样保留normal-return/源有效性条件，不能据checked推断初始化已发生。顶层lifetime、历史保持、可达性、opaque effects和deploy均未建立；顺序/复制效果/cleanup各有独立状态。
- 主代理补测试/文档并审diff，GPT-5.6 Sol实现源码。审阅中纠正新测试对ForStmt空占位的过强期待：改用goto_flow检验父checked/order unknown，原strict拒绝不放宽。

## 本地验收

环境WB_NATIVE_CAPTURE_PLUGIN=$PWD/artifacts/capture-plugin-cleanups-gYQ3gz/libwavebridge_capture_plugin.so；WB_NATIVE_CAPTURE_COMPILER=/opt/AMD/aocc-compiler-5.1.0/bin/clang++。

- make check：693项，退出0；PYTHONPATH=src python3 -m unittest discover -s tests -p '*clang*.py'：217项，退出0；make demo退出0。
- 定向object-use原生回归33项通过，git diff --check通过。
- 日志与脚本在artifacts/wb-object-use-structure-zMjhda/{tests,clang,demo,compatibility}.log。
- compatibility.py使用同一真实native AST，38个函数×3协议共114份完整报告与fdf3681旧源码一致。compatibility.json SHA256 fa78b9845aa79d1712e2798e108271114b78ace529f901e4a772e9b12b2df45c。
- 实现object_use_closure.py SHA256 edcc8c59f6f85f1281fa641b5390619ad48c9c7a2b3fa4a4d6c49a033bb93c15，与兼容性报告匹配。
- 测试patch条件copy/identity入口为raise仅验证依赖方向，真实Clang/native及结构恢复未mock。覆盖合法direct/多分支/captured路径、写入/别名/地址逃逸、属性未知、元数据缺失/错绑、预算和输入不变性。
- if(false)中的source与copy结构checked，但CPU实际复制计数0；条件初始化和lifetime未知边界保留。真实side-effect temporary使cleanup unknown而父结构checked；goto使order unknown，opaque调用效果仍未建立。

## 生产验收待完成

- 新独立组合尚未在完整生产TU上完成重放，不把此前条件组合结果计作本轮证据。没有GPU执行。
- production.py已准备：读取固定完整AST及外部ABI/初始化选择域，不读取alive/capture协议或旧成功子报告；重新运行新组合，独立核对父/顺序/效果/cleanup状态。
- 提交后启动，句柄记录同目录NEXT.md，运行中冻结src并核对77个实现哈希；不要因观察超时启动副本。
- 下一步先核实终态，再审剩余生命周期/历史保持义务；本轮依赖拆分不代表这些义务已被证明。
