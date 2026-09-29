# HIP 构造器默认可见性支持（2026-09-30）

基线9100afe，分支wb03-source-ast。修改constructor_effects的record属性
分类，不修改初始化域或复制效果检查，不填入[0,31]。

## 支持范围与依据

仅接受VisibilityAttr、visibility=default、无inner表达式；implicit/inherited
若存在必须为bool。观察记录保留原属性。其它属性、hidden/protected、缺值、
属性携带表达式全部unknown；原record/字段/initializer/空构造体门槛不变。

[Clang Visibility定义](https://clang.llvm.org/doxygen/Visibility_8h_source.html)
将default visibility描述为动态链接器可见的普通对象。这里据此仅将其归为
不增加选定构造体表达式的属性，不据此证明动态链接选择了该实现。
报告新增linker_resolution_and_interposition=not_established。
下游组合仍依赖“选定构造器确实被调用并正常返回”的外部前提；不能把
constructor checked或对象组合结果升级为链接/机器码验证。

## 重放

```bash
PYTHONPATH=src:. python3 -u -m experiments.softmax_launch_native \
  --profile hip --threads-object \
  --native artifacts/wb-hip-native-20260927-01/native.json \
  --output artifacts/wb-hip-threads-visibility-20260930-01/report.json
```

输入SHA `46ac52b1c672fadd0e5a66bb3ab380373e0cd69929713d96e7010f375a0cd63e`；
报告SHA `5e5bcddef841a5be3725cf0d0a4afaf9c2f5f67100b636097b9730a76ef232ef`。
输入/src/driver前后稳定、结束后复核一致。大工件仅在本地。

同一HIP对象：constructor_effects由record_attribute_unsupported变为checked，
constructor_fields为recovered；constructor_source现在unknown/selection_domain_missing。
对象仍unknown/fresh_conditional_object_initialization_not_checked。
两个host尺寸实参仍symbolic，未建立copy inventory、调用求值/历史保持、
配置值或lane域。无GPU、新编译采集、性能或部署结果。

## 验证

真实Clang fixture新增显式default属性的普通构造体与含额外写入构造体。
SDK23运行8项通过：正例checked，写入负例unknown，属性变异保守拒绝。
系统旧Clang首次正例未通过，因为其JSON省略visibility；保留checker拒绝，
测试改为显式验证这一缺证据边界，没有从源码拼写补填AST。旧版8项也通过。
测试可用WB_VISIBILITY_COMPILER选择编译器；未配置时使用PATH clang++。
Sol只读复核无阻断；链接解析前提不由此消除。
最终make check：1279项、96.867秒、无跳过，日志 `/tmp/wb-visibility-check.log`。
本轮以WB_VISIBILITY_COMPILER指向SDK23，native其它套件使用各自SDK23/AOCC17
匹配插件；不称全量SDK23验收。make demo和git diff --check通过。
