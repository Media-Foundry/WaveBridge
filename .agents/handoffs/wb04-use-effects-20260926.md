# 显式源引用的复制效果组合

- 日期：2026-09-26；分支 `wb03-source-ast`，基线 `f707919`。
- 中文、直接commit/push，不建PR，不合并master。前一代码提交4d68f51的CI
  36230032233已success；f707919终态查询遇EOF，不宣称通过。
- 修改已有object_use_closure，新增单一source_reference_use_effects子报告。
  不扩模块、不改变原v1主status含义，不混入source_order/parameter_target。
- 新子报告仅在fresh引用闭合/立即调用检查后消费本次direct record-copy和
  captured capture-source内部copy的local_copy_effects；root/source/copy ID、
  route、完整集合和重复项均核对。任一未知导致效果组合unknown。
- 真实maybe_unused copy参数是支持子集外的负例，不声称该属性导致运行时写入。
  direct/captured均保留旧closure/order checked而新效果unknown。
  合成子报告缺项、重复、错source/root/route/effect标签只作为组合绑定回归，
  不称真实可编译反例。公开入口不接受调用者提供的子报告。
- GPT-5.6 Sol只读复查未发现阻断问题。初始化阶段this逃逸已有窄constructor
  门控，不增加重复分析器；后续需明确C++对象模型与生命周期义务。

## 验证

```bash
export WB_NATIVE_CAPTURE_PLUGIN="$PWD/artifacts/capture-plugin-cleanups-gYQ3gz/libwavebridge_capture_plugin.so"
export WB_NATIVE_CAPTURE_COMPILER=/opt/AMD/aocc-compiler-5.1.0/bin/clang++
make check
make demo
PYTHONPATH=src python3 -m unittest discover -s tests -p '*clang*.py'
```

23项定向、661项CPU、185项Clang专项及demo全部退出0。后三项日志为
`artifacts/wb-use-effects-yPUsu3/{tests,clang,demo}.log`。未运行GPU。

## 完整TU重放结果

命令：`WAVEBRIDGE_JSON_HASH_MODE=one-shot PYTHONPATH=src python3 artifacts/wb-use-effects-yPUsu3/check.py`。
exec session16078已退出0，PID200351已结束。日志run.log，终态report.json。
固定输入 `artifacts/wb-vllm-cleanup-native-a1pI0L/ast.json`；SHA256
`f80432e744686fdc1390308073a3cd7e1b1d1ba5afd065198dcc292ab21ee9ee`。
只从原协议记录读取外部ABI/输入域/capture条件，不消费旧成功子报告。
运行前后核对77个src实现文件；运行期间不得改src，不因观察超时重启。
本次主引用闭合、source_order与source_reference_use_effects均checked；3个
真实captured copy全部通过。耗时469.3231417539937秒，77个实现文件前后
哈希一致，并用sha256sum --check复核当前源码仍完全匹配。
报告SHA256：`5c1d0e3f205cd0b1989a1d2166941c9e8a35d5385b7d094d9f4ce4391c157756`。
代码b562c42已推送；其远端CI终态查询遇EOF，暂未核实。无GPU执行。

## 保证与下一步

只签AST角色上的源字段读取/目标初始化/额外地址发布分类；捕获身份仍受外部
协议约束。动态source/destination非重叠、隐式lifetime、不透明调用影响及
source历史值保持全部未建立。普通局部copy无需parameter_target成功；与实际
launch配置关联时另检查该项。Sol后续只读核查建议下一项从capture协议移除
closure_instances_from_recorded_lambdas_assumed，改用fresh立即lambda与copy
语义祖先调用链建立closure来源。需处理协议版本兼容，不能仅删键后放行；
具名、传出、返回以及嵌套外层非立即调用应拒绝。source_initialized_alive与
same-activation暂时保留，不把origin建立偷换为生命周期保证。

本轮另修正README/docs/architecture中仍称compiler仅文档、frontend仅人工模型
的旧描述，并明确主/子报告的不同保证。只改文档，不改已重放源码；文档通过
git diff --check。不以no_alias/value_preserved布尔假设换取历史成功。
