# 当前 HIP 工具链的 builtin lowering 探测

2026-09-27，基线`7621fc9`。本轮复用既有builtin_value_probe与同一份合成
builtin_values.cu，新增独立固定HIP配置；不替换生产kernel、不运行GPU。

## 编译证据

```bash
PYTHONPATH=src:. python3 -m experiments.builtin_value_probe \
  --profile hip-gfx1100 \
  --config experiments/probes/builtin-values-hip-gfx1100.json \
  --output-dir artifacts/wb-hip-builtin-probe-20260927-01
```

会话63465正常结束，status=observed、inputs_unchanged=true。报告SHA256：
`1c430a65f1385692350d68f35b5db8cd896a6cccc40ac03f686d4ff6ac2dc2d3`。
直接使用最终W7900 pilot的同一个实际Clang二进制，SHA256为
`f80bad7383249331b12bd9bfdfdfe821a9d362393d08e9489d5976681e9e4616`。
目标gfx1100、HIP device-only，显式包含HIP runtime与Clang runtime wrapper。
这是独立合成TU，不声称与原生产TU的编译闭包相同。

| 配置 | IR SHA256 | 依赖记录 |
| --- | --- | --- |
| O0 | `3e92a15b4fc6dce07e985372848350c8800b03e7429f77d275a84f64b0e3ddd0` | 308项，observed |
| O2 | `0d664ff798dd71ebe32f1fa1cd35a1f4fed53a7c64de1da88e9a7197d928c80e` | 310项，observed |

O0中直接builtin探针分别为`ret float +inf`及`ret float +qnan`；
numeric_limits包装仍调用对应C++方法，而这两个方法的函数体分别直接返回
上述常量。O2中四个探针均为常量返回，并带memory(none)属性。
外部调用对照仍调用wb_unimplemented_leaf；写入对照仍包含对output的store。
O2写入对照属性为memory(argmem: write)，不能因为它返回inf就删除写入效果。

只检查所列函数，不将整个O0模块说成无副作用；模块还包含HIP runtime的
assert/hostcall等其他定义。编译器优化结果是观察，不是源到IR或机器码验证。

## 原生采集缺口与版本差异

本地限定搜索在/opt、/usr/include、Conda include、SDK include及仓库工件中，
只发现AOCC17的Clang开发头，未建立当前SDK Clang23的匹配插件构建路径。
该SDK有libclang-cpp.so.23.0git，库存在不代表开发头齐全或插件ABI兼容。
没有安装新工具链、修改SDK或加载版本不匹配的插件。

SDK版本输出标识ROCm llvm-project提交
`8f497e0992fb7513f7f78a6f6b6f1056c375e961`。最小host文本AST探测输出
BuiltinAttr编号1042；原HIP JSON AST只含隐式BuiltinAttr，没有数字builtin ID。
这两份输出不能按指针ID拼接，也未写入伪造native envelope。
原HIP builtin DeclRefExpr的valueCategory为lvalue，现有受限native checker
要求prvalue；这是待用匹配原生证据回归的版本形态差异，本轮没有放宽规则。

后续更正：匹配插件生成的真实HIP原生工件中，该builtin引用为prvalue，现有
结构检查器可直接支持。此前JSON中的lvalue观察不能归纳成Clang23版本规则；
两份工件差异成因尚未验证，见[原生构建与采集记录](clang23-native-build-20260927.md)。

## 结论与下一步

本轮为当前HIP编译配置下的NaN/inf leaf假设提供编译观察，而不是自动消除
生产源码调用效果义务。source_program_checked/deployable仍false，上一轮
两个输出循环的unknown不升级。下一步需建立匹配的原生采集或单独明确可信
基础的前端身份路径；不得按函数名白名单或跨AST指针ID补齐证据。

新增profile保持原CUDA默认和独立配置/编译器哈希约束；3项新回归覆盖HIP
观察边界、未知profile和跨profile配置误用。专项8项通过，均为driver fixture，
不是设备证据。

完整验收启用匹配AOCC原生插件：1215项CPU测试通过（92.164秒，无跳过），
make demo、git diff --check通过。日志为/tmp/wb-hip-builtin-check.log与
/tmp/wb-hip-builtin-demo.log；不是远端CI结果。
