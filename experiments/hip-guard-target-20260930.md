# 守卫候选 block copy 的按值形参目标

基线`72564e3`，分支`wb03-source-ast`。沿用同一冻结候选，不生成新源码，
不重编译HIP、不链接或执行程序/GPU。

## 已定位的输入边界

上一轮真实copy局部效果checked，parameter_target却因
`copy_target_function_children_unsupported`为unknown。核对完整原AST确认
callee `0x2caec780`除四个ParmVarDecl外仅有`VisibilityAttr(default)`。
该声明是`__hipPushCallConfiguration`，检查器不按名字推断配置语义。

本轮按值目标绑定对这一属性采用与constructor局部效果相同的窄规则：
明确default、无子节点、implicit/inherited若存在必须为bool；记录原属性。
唯一callee、完整参数数量、精确参数位置/类型、非模板/重声明等门槛保持。
所选参数不允许默认实参；其它参数有默认值不等于它们的求值与效果已经检查。

## 重放命令

```bash
PYTHONPATH=src:. python experiments/softmax_launch_native.py \
  --native artifacts/wb-hip-query-guard-candidate-20260930-01/native.json \
  --output artifacts/wb-hip-guard-target-20260930-01/report.json \
  --profile hip-guard --threads-object
```

输入native SHA256：
`df7d0b37e1d7ca16977f6d133285705d004a655e880b87b635148a373816e8b5`。
block copy`0x7769241d4cc8`，源对象`0x77692424c3c0`，配置callee`0x2caec780`。
实现record_copy_check.py SHA256：
`bb18d751c8b000662eaa5b713020447721161b036e0f4c1c213384d14e35428e`。

## 回归与边界

Clang23/17复制专项各32项，分别6.647/6.686秒通过。真实fixture包含default
visibility的按值callee及另一个默认参数，正例保留other-argument、callee-body、
linkage/API等未建立字段；缺观测、hidden/protected、child、坏bool、未知属性
变异保持unknown。专项日志为`/tmp/wb-copy-target-visibility.log`及
`/tmp/wb-copy-target-visibility-clang17.log`。Sol只读复核无阻断。
这不是把运行库调用视为纯函数；对象历史、switch/grid分支、源存活及其它
实参求值仍需独立检查。局部object boundary也不是动态生命周期或值保持证明。

## 实际结果

重放完成，报告SHA256：
`34d20ae4506ee9727d3ad8cb9f1e6c5ee7115467656f7be5bb52e082bd651297`。
inputs_unchanged=true。launch、copy局部效果、object_boundary、parameter_target
均checked；按值目标精确为callee `0x2caec780`的参数`0x2caec560`、位置1，
调用`0x7769241d4bb8`。这没有解除source_object_preservation或API/链接义务。
对象闭合仍unknown，原因`fresh_conditional_object_initialization_not_checked`，
旧数值入口内部仍`selection_domain_missing`；不能把先前构造值域手抄成外部
协议替代fresh组合。configuration_values_established/source/deploy仍false。

最终全测1374项176.304秒通过，无跳过，日志`/tmp/wb-guard-target-check.log`。
与上一轮相同，visibility/unary/using-shadow/enum固定Clang23，native capture
固定Clang17；`make demo`、`git diff --check`通过。结束后再次核对实现与报告hash一致。
