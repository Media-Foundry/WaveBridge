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

## 完整生产TU独立入口终态（替代前述待完成状态）

- 实现5c1d9f43c07d9c80d2f969a81c940fcb82150074，已推送；CI 36236082670全部success，含Clang18原生专项与Python3.11/3.12。
- 会话73772退出0，耗时424.9957761760015秒。工件production.json SHA256为e84d047ca22bfc7c2572c7d13880fefeb0e0a74db665ef0e0aca20a06fffd3fb，目录仍为artifacts/wb-capture-structure-RIsswR。
- 同一固定完整生产AST三个copy 0x37382628/0x37388288/0x3738de68均fresh checked，copy_structure及object_boundary、closure_origin子报告均checked。
- 每个copy绑定两层立即receiver；共享外层lambda 0x373934c0，共四个不同lambda，不表示六次实际执行。均绑定函数0x3736fa78、body 0x373938c8、source声明语句0x37370ea0。
- 新入口只读取外部整数ABI，不读取capture/alive协议或旧成功报告；动态身份、source lifetime、历史保持仍not_established。whole_composition_replayed=False，gpu_executed=False。
- 77个实现哈希前后一致，终态后jq提取并经sha256sum --check --status复核退出0，源码冻结解除。

## 不可达代码的真实CPU边界对照

- 同目录unreachable.cpp将source初始化和立即捕获copy置于if(false)。真实Clang/native结构checked，CPU退出0且stdout为copies_executed=0。未执行GPU。
- 源SHA256 e334b11b2d2deb6dbc3e4d1a3ac60d1097b375f9e0d4215169674c7b3ec2c429；unreachable-final.json SHA256 caf7990bdd1a91b49488f6cccb5ebbefd3b6fbfd64adb9471725d8838adac2bd。
- 新入口保留lifetime/identity未建立；该例验证结构checked不推出求值发生，不是当前错误放行。
- 首轮脚本ABI漏列int，结果unknown/integer_type_missing_from_abi；补全ABI后的最终记录另存，未覆盖unreachable.json。此项为额外独立诊断，不增加687/211测试计数。
- 下一项按只读审计拆object_use_closure结构组合：复用semantic inventory，初始化completion继续conditional，不用它反推alive。必要回归为不可达、显式source写入、未知copy属性及具名/传出receiver。
