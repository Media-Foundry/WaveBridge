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

## 已启动的完整TU重放（待收取）

命令：`WAVEBRIDGE_JSON_HASH_MODE=one-shot PYTHONPATH=src python3 artifacts/wb-use-effects-yPUsu3/check.py`。
exec session16078，2026-09-26核实PID200351存活。日志run.log，终态report.json。
固定输入 `artifacts/wb-vllm-cleanup-native-a1pI0L/ast.json`；SHA256
`f80432e744686fdc1390308073a3cd7e1b1d1ba5afd065198dcc292ab21ee9ee`。
只从原协议记录读取外部ABI/输入域/capture条件，不消费旧成功子报告。
运行前后核对77个src实现文件；运行期间不得改src，不因观察超时重启。
本次终态未取得，不能把上一轮结构顺序成功替代新效果组合成功。

## 保证与下一步

只签AST角色上的源字段读取/目标初始化/额外地址发布分类；捕获身份仍受外部
协议约束。动态source/destination非重叠、隐式lifetime、不透明调用影响及
source历史值保持全部未建立。普通局部copy无需parameter_target成功；与实际
launch配置关联时另检查该项。先收取当前完整TU结果并核验哈希，再设计生命周期
与非逃逸组合，不以no_alias/value_preserved布尔假设换取通过。
