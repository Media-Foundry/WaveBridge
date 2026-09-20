# 交接：构造字段及条件整数转换

- 日期、分支、基线：2026-09-20，`wb03-source-ast`，`cc041f5`。
- 用户约定：中文，直接commit，无PR，未推送。
- 实现：constructor_fields从精确空body构造恢复FieldDecl到ParmVarDecl的位置映射，核对类型和可定位record字段完整性；不靠字段名猜测。source报告接入field_initialization。
- 独立检查：integer_conversion.check_interval检查显式源/目标位宽和signedness下的区间值保持；无analysis依赖。源域非法unknown，目标不能表示时rejected。
- 验证：`make check`206项通过，`git diff --check`通过；真实Clang字段交换被正确记录，body写入拒绝；小整数区间与枚举表示范围交叉核对。
- HIP：沿用源码入口命令，输出 `artifacts/wb03-source-constructor-fields-01`，两个构造都恢复x/y/z对应0/1/2，直接record字段完整，分析实现hash一致。
- ABI：`artifacts/wb03-abi-macros-01/report.json`记录同HIP编译入口执行`--cuda-device-only -dM -E -x hip /dev/null`的宏及原始输出，int32/long64/long long64。
- 条件证据：源码目录conditional-conversions.json绑定上述报告和checkerhash，256/1/1在显式int32→unsigned int32假设下checked；完整源码ABI绑定仍not_established。
- 未执行：新GPU/native64/性能实验；未宣称配置物理执行模式、坐标语义或完整源码正确。
- 下一步：将类型/目标契约和恢复出的具体转换一一绑定，建立实际配置字段值；仍须外部坐标/intrinsic语义及源/目标检查，G1差异验证未完成。
