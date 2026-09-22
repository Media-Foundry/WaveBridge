# 按值复制实参目标绑定

- 日期：2026-09-23；分支 `wb03-source-ast`；基线 `a56a314`。
- 中文、直接commit/push，不建PR、不合并master。基线远端CI已success。
- 上轮实际完整TU证据确定copy位于配置CallExpr实参而非VarDecl；本轮沿该路径
  实现，而非仅做局部变量目标的较易替代。

## 实现

在现有 `record_copy_check.py` 内增加 `parameter_target`，无新框架/服务。
先fresh字段关系和局部效果，再由copy的完整AST父节点自动恢复call ID、
精确callee declaration、形参ID与argument position，不读人工成功报告。
同ID副本核对，直接完整prvalue、F2P decay与函数签名精确，按值类型/alias一致；
参数属性/默认值、重声明、模板、间接调用、引用/额外wrapper和冲突均unknown。
既有主v1值关系不因该子报告未知而自动失败，也不会被子报告升级。

Sol复查指出：未绑定C++方言时，实参临时对象不能直接叫作最终parameter
对象。已修正 `target_kind` 为 `complete_prvalue_argument_for_exact_by_value_parameter`，
保留storage nonoverlap、physical ABI、callee/其他实参/cleanup/API/launch未知。
同时加入callee/reference valueCategory和多body畸形边界门控。

## 本地验收

```bash
export WB_NATIVE_CAPTURE_PLUGIN="$PWD/artifacts/capture-plugin-cleanups-gYQ3gz/libwavebridge_capture_plugin.so"
export WB_NATIVE_CAPTURE_COMPILER=/opt/AMD/aocc-compiler-5.1.0/bin/clang++
make check
make demo
PYTHONPATH=src python3 -m unittest discover -s tests -p '*clang*.py'
```

647项CPU、171项Clang专项和demo全部退出0，插件测试实际运行。
日志 `artifacts/wb-parameter-target-1HUXcC/{tests,clang,demo}.log`。
真实Clang源码测试覆盖按值/改名callee正例与间接/引用/模板未知；合成变体
覆盖错误类型/数量/ID/位置、冲突副本、variadic/模板/redecl、错误valueCategory
及多body，不把它们叫作真实编译成功的攻击程序。
开发阶段两项失败分别定位为新增代码变量遮蔽和新增fixture未定义callee导致
旧CPU执行测试链接失败；均已修复并重跑全部验收，没有删除既有CPU运行测试。

## 尚未建立

源码历史保持、source动态identity、按值参数storage nonoverlap及配置运行时
消费语义仍未知。没有GPU执行或自动适配候选；下一步组合必须保留这些义务，
不能把绑定了正确形参当成已经证明整个配置值来源和生命周期。

## 完整 TU 实际验收

```bash
WAVEBRIDGE_JSON_HASH_MODE=one-shot PYTHONPATH=src \
  python3 artifacts/wb-parameter-target-1HUXcC/check.py
```

exec session91759正常退出0；132.743178秒，77个Python实现前后hash一致。
固定输入 `artifacts/wb-vllm-cleanup-native-a1pI0L/ast.json` SHA-256：
`f80432e744686fdc1390308073a3cd7e1b1d1ba5afd065198dcc292ab21ee9ee`。
三个copy `0x37382628`、`0x37388288`、`0x3738de68` 的值关系、局部效果、
parameter_target均checked，位置均为1（从0开始）；精确callee `0x2135cd60`、
形参 `0x2135ca90` 与上一轮观察一致，但本次从完整AST重新求出，不消费旧结果。
callee无body，源码声明类型为按值dim3；不据此解释其运行时行为。

报告 `artifacts/wb-parameter-target-1HUXcC/report.json` SHA-256：
`77a0a84b5dcb7546f9150e64b91d546c6aa7097a859473695b3dc57721a6d895`。
同一固定vLLM原生TU与编译视图，未重采集；one-shot显式记录，未做相同任务
流式对照，不报告加速比。所有范围限制在报告中保留，部署false。
