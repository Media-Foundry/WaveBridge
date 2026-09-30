# 守卫候选的真实 launch 与 block 复制检查

基线`9190e20`，分支`wb03-source-ast`。本轮不生成新候选，不编译/执行HIP，
重放上一轮冻结AST。独立检查constructor字段值不等于建立对象历史或launch值。

## 命令与输入

```bash
PYTHONPATH=src:. python experiments/softmax_launch_native.py \
  --native artifacts/wb-hip-query-guard-candidate-20260930-01/native.json \
  --output artifacts/wb-hip-guard-launch-20260930-02/report.json \
  --profile hip-guard --threads-object
```

新profile固定native SHA256
`df7d0b37e1d7ca16977f6d133285705d004a655e880b87b635148a373816e8b5`
与kernel`0x7769241d57f0`。原CUDA/旧HIP profile与工件不变。
kernel依原有预声明模板实例float/float/float/7/0/0选取，不按检查结果选例。

选中launch`0x7769241d5b08`，配置函数`0x2caec780`，block槽position 1
为copy expression`0x7769241d4cc8`，其source为上一轮构造的对象
`0x77692424c3c0`。四个配置槽ID分别为`0x7769241d4c98`、
`0x7769241d4cc8`、`0x7769241d4cf8`、`0x7769241d4b78`。
完整TU仍记录22个未解析launch位置，不能把单个精确绑定当全TU覆盖。

## 首轮发现与修复

01报告保存修复前结果：launch绑定checked；copy结构恢复三个同FieldDecl
映射，但局部效果因`declaration_effect_subset_unsupported`为unknown；
对象闭合则因`fresh_conditional_object_initialization_not_checked`为unknown。
该报告SHA256为`477d3cd596605344cfa0f2e5fca0da1fd495eb13630ec268f0b4fcc3b67facf5`。

直接检查原AST确认record `0x2ca675a8`的`VisibilityAttr`为default，
copy constructor `0x2cb32da0`是隐式defaulted复制构造，拥有三个成员初始化与空body。
record_copy局部效果原先拒绝所有record属性；现与constructor_effects既有
策略一致，仅允许有明确default证据、无children、布尔flag类型正确的visibility。
原始属性被记录，缺证据/未知属性仍unknown；不证明链接或符号插入行为。

## 未解除的真实路径义务

真实对象声明后是switch，而非唯一紧邻copy。对该函数AST的显式引用检查
发现11个case各两次引用：一次block槽copy，另一次grid计算中传给helper的copy。
不能为迁就简单checker将真实程序替换成单次使用示例，或忽略grid侧求值。

对象闭合的旧初始化入口仍要求selection_domains；本轮没有把先前数值报告
手工抄成外部域以绕过它。需要后续结构/数值接口组合，同时检查真实switch路径、
所有相关副作用、copy求值及cleanup、生命周期和配置API语义。
threads_slot_copy_effects仅选中block槽的独立局部检查，不覆盖其余21次引用。
配置值、lane family、源程序与部署标志均保持false。

## 验收

驱动6项编排测试使用mock，仅说明profile隔离、精确槽位传参与unknown传播，
不是源码语义证据。真实Clang复制专项各30项通过：Clang23 6.355秒、
Clang17 6.380秒；旧编译器缺visibility观测时必须unknown，不伪造属性。
专项覆盖合法属性、构造体写入、missing/hidden/protected/child/坏bool/未知Attr。
日志`/tmp/wb-copy-visibility.log`、`/tmp/wb-copy-visibility-clang17.log`。
Sol只读复核无阻断。修复前全测1370项不作为最终语义变更验收。

最终02报告SHA256：
`d9852047c750787651d96b4ae2227be96389da33acc68828f2108f7b0c734888`。
launch绑定与所选copy局部effects均checked，inputs_unchanged=true。
但copy子报告object_boundary仍unknown（copy_destination_not_plain_automatic_record），
parameter_target仍unknown（copy_target_function_children_unsupported）；父级局部
checked没有替代这两项义务。对象闭合仍为前述selection_domain_missing链。

冻结实现SHA256：record_copy_check.py为
`094578047cc09dc78ff72885668a64320fd1e4a85a4ef06aba17a90d8fb16da2`；
softmax_launch_native.py为
`827d63b4e3256be86d306be38744c829c0b9c387d5172d1df40a5938f7f948f6`。

最终全测1372项178.032秒全部通过无跳过，日志
`/tmp/wb-guard-launch-check-final.log`；工具链变量与上一轮全测相同，
visibility/unary/using-shadow/enum使用Clang23，native capture使用Clang17。
`make demo`与`git diff --check`通过。所有运行结束后再次核对02报告hash一致。
