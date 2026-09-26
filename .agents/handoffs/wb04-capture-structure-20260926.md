# 独立捕获结构恢复

- 日期2026-09-26，分支wb03-source-ast，基线6016720。中文回复、直接commit/push，不开PR。
- capture_source_check.py新增inspect_structure，schema capture-source-structure/v1。调用record_copy.inspect_effects，不调用条件值check，不接收alive/source-valid协议。
- 共享_recover_structure恢复精确native by-reference链、语义body路径、立即receiver祖先与普通函数body绑定；旧check复用它并在外层保留v1/v2/v3原动态条件、范围和失败诊断。
- 新报告copy_structure、静态capture_chain、activation_binding、closure_origin；动态identity/lifetime/value preservation均not_established，无identity_completion。嵌套lambda-invocation报告保留旧动态前提，但本入口只消费静态ID/路径，不升级receiver身份。
- Sol子代理实现源码，主代理补真实native回归并审阅diff。测试把条件值入口patch为raise只用于检验依赖方向；实际结构恢复与Clang/native采集未mock。
- 正例包含立即/嵌套、capture initializer求值及递归；具名/传出/返回/by-copy/引用别名等unknown。真实unused参数属性保证旧条件接口仍checked而新结构unknown。先写source后copy仅结构checked，未声称历史保持。

## 本地验收

原生环境：WB_NATIVE_CAPTURE_PLUGIN=$PWD/artifacts/capture-plugin-cleanups-gYQ3gz/libwavebridge_capture_plugin.so；WB_NATIVE_CAPTURE_COMPILER=/opt/AMD/aocc-compiler-5.1.0/bin/clang++。

- make check：687项，退出0，tests.log。
- PYTHONPATH=src python3 -m unittest discover -s tests -p '*clang*.py'：211项，退出0，clang.log。
- make demo：退出0，demo-final.log；git diff --check通过。
- 目录artifacts/wb-capture-structure-RIsswR。
- compatibility.py将同一真实native AST的21个函数、3个协议共63份完整JSON与6016720旧源码对比；最终compatibility-final.json全部一致，SHA256为400d6638af1d908d5f97b497f616a73804a307040a698ace91fb9f599f593dca。
- 最终实现文件SHA256为056879647585d7babfca0d8d68ac8491a1707bed6cb56f6e5ca7f3a8aeb8d4ea；与兼容性报告匹配。
- 保留compatibility.json中间失败记录（当时非引用捕获reason变化，已恢复）；随后一次重复写该路径被exclusive-create拒绝，不能当作终态。正式验收只使用compatibility-final.json及对应日志。

## 尚未完成与下一步

- 未运行GPU、未重放完整生产TU新入口；旧生产结果不算本次证据。
- production.py已准备：固定同一完整生产AST，旧报告仅提供ABI，不读取alive协议或旧成功子报告，独立检查三个copy；工件exclusive-create并核对77个实现哈希。
- 提交后启动生产重放，句柄记同目录NEXT.md；运行期间冻结源码，不因观察超时启动副本。
- object_use_closure仍消费旧条件报告；下一步在生产核验后继续拆结构组合与条件值组合，而不是直接删alive。
- source lifetime、其它scope cleanup、opaque调用、历史值保持、部署与跨波宽适配均未因此建立；无新外部阻塞。
