# HIP 循环关系与调用边界重放

2026-09-27，基线`baa047d`。复用现有检查器，不修改生产分析算法、不新增GPU结果。

## 协议与执行

固定上一轮完整HIP AST及intake报告哈希；选择同一模板实例，不按成功结果选点。
遍历其全部8个ForStmt，分别检查原始循环头及直接退出分区。只有退出分区
checked时才调用现有guarded-work检查器，开启静态分支及受限嵌套循环支持。
不提供外部调用效果协议，不把旧CUDA原生观测移植为HIP证据。
另复用既有调用清单工具，记录语法直接调用关系；这不是动态可达性或效果证明。

```bash
PYTHONPATH=src:. python3 -u experiments/softmax_hip_relations.py \
  --ast artifacts/wb-softmax-hip-intake-20260927-01/ast.json \
  --intake artifacts/wb-softmax-hip-intake-20260927-01/report.json \
  --output artifacts/wb-softmax-hip-relations-20260927-01
```

会话12650正常退出0，status=observed，inputs_unchanged=true。
报告SHA256：`ad1364304676a635f489b0275d1cd7204dac706cbd7af553d59199f167d8cf93`。

## 结果解释

8个循环头均observed，仅描述头部，不建立循环体保持性、整数溢出域或完整递推。
两个输出循环分别具有leading-break及trailing-else-break结构；静态布尔
模板参数可由已有路径处理，但循环体仍在调用效果处保留unknown。
其余6个循环没有该检查器要求的直接break分区，不适用此入口，不等于程序错误。

两个输出循环的header connection均checked；静态选择分别记录2处及1处决策。
两者均停在同一个源码范围offset 8811–8849，对应call `0x7b36f84c9aa8`、
声明`0x2ce0d9b0`的`std::numeric_limits<float>::quiet_NaN()`。
调用身份由现有解析器绑定，效果尚未建立，不能把`sum[i]==0`分支视作不可达。

语法调用清单包含30个声明节点、39条调用边，预算未耗尽；其中9个节点没有
可见定义，包含builtin及OCKL调用。36条边具有解析目标，另外2条静态方法
引用形式不支持、1条缺少member callee声明。上述数量不代表动态调用次数或
完整GPU执行调用图；旧默认归约发现的21处未解析与这里的库存范围也不同。

保留原始报告各层前提；source_program_checked、deployable均false。
int32是外部ABI假设，合法执行、存储不别名等检查器前提没有通过本次重放证明。
这是一份既有development输入的分析，不是新增独立holdout或自动适配结果。

## 后续范围

优先针对精确调用建立同HIP工具链的身份及效果证据，而不是给函数名加白名单。
初步文件检查发现当前SDK具有libclang-cpp.so.23.0git，但其llvm/include目录下
未找到clang/AST/ASTContext.h；这仅是该路径的观测，不代表系统所有位置均无
匹配开发头。不得将AOCC17插件直接加载进此Clang23工具链。

## 验收

新增4项绑定单位测试，明确属于fixture而非源码恢复证据。完整CPU验收启用
匹配AOCC原生插件，1212项通过（93.883秒，无跳过），make demo及diff检查通过。
日志：`/tmp/wb-hip-relations-check.log`、`/tmp/wb-hip-relations-demo.log`。
本轮没有远端CI核验或GPU执行。
