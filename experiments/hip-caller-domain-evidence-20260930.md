# 从早返回守卫恢复 host 调用的离散实参域

基线`994bbde`，分支`wb03-source-ast`；本轮不运行GPU。

## 新检查与原有检查的区别

`parameter_entry.check_guarded_argument`不要求调用者入口已给定数值域。
它检查同一函数体直接语句中的自动`const int`声明、早返回if、直接调用顺序；
从guard正常落下这一必要条件恢复有限值集合。仅沿builtin `||`的false蕴含，
接受完整由同一局部量`!=`整数字面量构成的`&&`树。额外未知conjunct不能省略。

函数内该局部对象的每次引用都必须是普通LValueToRValue读取，取址、引用绑定
和其它用途拒绝。跳转、标签、switch、asm、协程、捕获、显式生命周期相关
不支持语法保守拒绝。其它API调用不被声明为纯函数；结论依赖源程序有效、
对象生命周期不被替换、普通顺序执行、无非局部跳转/异步干扰的显式前提。

所选实参与精确callee形参按位置绑定为plain int。报告仅证明：
**若该调用正常到达，所选参数传入值属于恢复集合。**
不证明调用必达、其它实参无副作用、整个调用安全、二进制或部署正确。
AST层callee身份已精确核对；该声明确实对应实际运行实现仍是链接前提，
不是本轮验证过的运行时事实。

## 真实 HIP 选点

固定AST输入SHA256：
`46ac52b1c672fadd0e5a66bb3ab380373e0cd69929713d96e7010f375a0cd63e`。
实际caller `0x2248f4c8`，columns声明`0x2248fb88`，调用`0x22508f48`，
callee `0x22508c60`，所选参数`0x225088a8`位于零基位置2。
驱动从此前fresh恢复出的callee/parameter关系枚举调用与直接if，不按名字匹配；
所有候选guard的unknown仍保留，不能把局部成功当成所有caller均覆盖。

```bash
PYTHONPATH=src:. python3 -m experiments.softmax_launch_native \
  --profile hip \
  --native artifacts/wb-hip-native-20260927-01/native.json \
  --output artifacts/wb-hip-caller-domain-20260930-01/report.json \
  --host-dimensions --power-input-domain 65 128
```

新caller_guard_checks与既有entry_to_shift_check暂时并列。虽然预期前者恢复
端点集合{65,128}，仍未正式组合成后者的入口协议，也不替代历史GPU面板审计。
本轮不把外层call_domain_established或source_program_checked改成true。

## 回归范围

真实Clang测试包括含未知其它predicate的OR正例、两个实参位置、额外conjunct、
取址/引用逃逸、goto绕过、mutable local、错误实参、错误位置、预算与身份冲突。
fixture正例证明的是源码必要条件，不是运行时数值或GPU结果。

## 实际结果

报告SHA256：`8a3e36a5dd8bf3d901004405220a6d3965537b134c2c4fc5ad9a3268570742e2`。
`inputs_unchanged=true`。6个候选if中，`0x22494e28`条件checked，恢复
`argument_values=[65,128]`，绑定参数`0x225088a8`，7个local引用全部通过
普通读取闭合检查。其余5个guard保持unknown：位置不支配或无可恢复有限域。
这里的1/6只是同一函数内诊断候选数，不是kernel覆盖率或语料接受率。

1305项完整CPU测试99.193秒通过、无跳过；日志`/tmp/wb-caller-domain-check.log`。
使用既有SDK23 visibility/unary/using及AOCC17 native插件组合。定向真实Clang
3项、demo/diff通过；Sol只读复核无阻断。重放期间源码/驱动冻结，未执行GPU。

下一步可将此精确call/parameter的端点集合与entry_to_shift正式组合，从而
替换当前手填入口区间前提；不能只判断两份报告都checked便宣称组合完成。
