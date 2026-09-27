# 从实际执行的 HIP 工件重新进入分析

2026-09-27，基线 `58695d0`。本轮不运行GPU，不复用旧CUDA AST。

## 输入绑定

入口固定上一轮最终10号pilot报告SHA256
`f53b5800c54e8ef5ec459b7734e3c4edf0a6064e8e519357881926e28b78cab2`，
fresh复核原始输入、派生文件、binary、编译wrapper与已观测SDK文件字节。
这不是接受任意自报成功的JSON作为证明，固定报告只用于选取既有数值工件。

采集仍用相同compiler wrapper，保留C++17、O2、gfx1100、显式width32和
include目录；移除save-temps/link/output选项，改为device-only、syntax-only
AST采集。源码没有重新改写，使用pilot目录中的cpp、派生上游头与compat头。
int_bits=32继续是显式整数ABI假设，不由物理波宽32推导。

```bash
PYTHONPATH=src:. python3 experiments/softmax_hip_intake.py \
  --pilot-report artifacts/wb-softmax-hip-pilot-20260927-10/report.json \
  --output artifacts/wb-softmax-hip-intake-20260927-01
```

会话62492正常结束，frontend=collected、status=analyzed。
report SHA256：`e0f3691cd2a4952193770cf251e7414d2be9ea4af11b4776967f7e0da9e091b9`。
AST工件SHA256：`ae7cb74e0b35a40ab14a42a9f5c763be7279f95ef7586e30513e92508b80ad11`。
334个依赖文件observed，toolchain trace observed；三份执行源码文件均在
同次依赖清单中且hash相同。前后输入与分析实现相同，结束后复核driver依赖一致。

新kernel ID为 `0x7b36f84eb490`，选点仍依据冻结的float/float/float/7/false/false
模板参数，不依据分析成功挑选实例。其mangledName与pilot编译metadata的
选定kernel相同。新launch ID为 `0x7b36f84eb7a8`。ID仅在本次AST有效。

## 实际分析结果

| 入口 | 本次观察 |
| --- | --- |
| 默认列循环恢复 | 8个循环中1个recovered，6个call_in_body，1个unsupported_control_flow_in_body |
| 归约发现 | 21个未解析调用：18个缺唯一可见定义，2个调用种类不支持，1个缺member callee声明 |
| 归约候选 | 0个已恢复XOR候选；不能从analyzed推断完整发现 |
| launch发现 | 选定实例1处；另22处未解析位置原样保留 |

这是默认恢复器的覆盖观察，不代表其他更专门的条件checker都不能处理这些
循环。SDK builtin/member包装、外部math和functor调用仍需在本次新AST上
分别建立边界；不能搬用旧CUDA声明ID或将18个数值通过当缺失语义的替代物。

## 局限与下一步

同源码文件、同显式编译设置和观测SDK字节的重新采集，不等于证明原binary
构建时全部依赖闭包相同，也不是最终机器码验证。报告明确保留
binary_build_dependency_closure_established=false、source/deploy=false。
现有手工HIP shim、default stream与width32专门化边界继续有效。

下一步复用现有模板/static-branch与条件效果检查路径，对本次HIP AST中
真实拒绝点逐项检查，并连接唯一launch。先检查已有机制能否迁移，不先按
新kernel名字填关系模板或重造验证器。原始报告与紧凑结果索引均保留。

## 回归

3项绑定单位测试通过（主树0.038秒）：临时manifest正常绑定、五类文件改动
拒绝、未完成/不稳定报告拒绝。它们是绑定fixture，不是模拟GPU结果。
GPT-5.6 Sol提供测试及只读复核；真实AST证据由上述单独采集建立。

完整验收命令：

```bash
WB_NATIVE_CAPTURE_PLUGIN=artifacts/wb-native-template-OqD1PQ/libwavebridge_capture_plugin.so \
WB_NATIVE_CAPTURE_COMPILER=/opt/AMD/aocc-compiler-5.1.0/bin/clang++ make check
make demo
git diff --check
```

1208项测试通过（92.433秒，无跳过），check会话26637正常退出0；demo及diff
检查通过。日志位于本次工件目录的check.log、demo.log。原生插件用于匹配的
AOCC回归，不加载进HIP SDK Clang23；这些测试不执行GPU，也不是远端CI结果。
