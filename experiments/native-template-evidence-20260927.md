# 模板实例中的原生对象与构造关联

2026-09-27，wb03-source-ast，基线8601ed5；无GPU。

## 发现与处理

固定旧工件wb-column-builtins-twz82w/native.json包含r声明0x19538580及
构造表达式0x19538618，但local_record_objects没有该变量的观测。插件
RecursiveASTVisitor此前未显式开启模板实例遍历。缺观测不能解释为无析构，
也不能凭Max名字、空对象或ctorType推测选中的构造函数。

本轮开启shouldVisitTemplateInstantiations，并新增constructor_calls：原生
getConstructor精确关联构造表达式、构造声明、所属record及有序实参ID，
记录isTrivial与isDefaultConstructor属性。其语义仍为身份/属性观测，
不证明构造实参效果、存活、正常返回或动态析构时序。覆盖仍标记非穷尽。

## 构建与重采

```bash
/opt/AMD/aocc-compiler-5.1.0/bin/clang++ -std=c++17 -fPIC -fno-rtti -shared \
  compiler/frontend/native/capture_plugin.cpp \
  -I/opt/AMD/aocc-compiler-5.1.0/include \
  -o artifacts/wb-native-template-OqD1PQ/libwavebridge_capture_plugin.so
```

调用wavebridge.frontend.native_captures.main：source为
benchmarks/intake/pytorch-softmax-harness.cu，compiler与compiler_args
原样读取artifacts/wb-pytorch-softmax-KhwXBa/config.json，timeout=180，
plugin为上述新产物。输出artifacts/wb-native-template-OqD1PQ/native.json，
实际编译命令、输入前后哈希及依赖清单保存在该报告中。采集collected。

```bash
PYTHONPATH=src:. python3 experiments/softmax_template_objects.py \
  --native artifacts/wb-native-template-OqD1PQ/native.json \
  --output artifacts/wb-native-template-OqD1PQ/selected-object.json
```

selector复用原先固定的float/float/float/7/false/false模板实例选择规则，
不按检查是否成功选案例。沿max_value实参与直接callee找到helper局部构造，
记录精确绑定；这不是跨工件ID对应算法，也不是新的留出谱系。

| 工件 | SHA256 |
| --- | --- |
| 插件源码 | `21f2b37693c8ff3943f6d9967de2a12363d3cd5e7994c8e0be94107d05ca235a` |
| 插件二进制 | `3af978b8b2a7d82f32157d659a7ed6e99c6a3d4852c2e615ff100db3c9a35898` |
| 新native工件 | `a59c12247f796fe2034ba03ecc43782f77ac3942496b18a140ceacbb24c7ff45` |
| 选点观测报告 | `6422c9b5cfe5a12aefab75a300f59c76415ec31d815ece46192aa0bb8787b203` |

## 真实观测

- caller 0x30d762e0，调用0x30de0078，helper 0x30dc6c48。
- r变量0x30dcdae0，直接compound 0x30dce648，record 0x30d87bc8。
- 构造表达式0x30dcdb78精确关联构造声明0x30d88228，实参为空。
- 原生构造属性is_trivial=true、is_default_constructor=true；AST声明为
  implicit、defaulted的void() noexcept。
- 局部对象自动存储期观测为true、has_nontrivial_destructor=false。
  destructor ID为null；不能只用这个null推断无析构效果。
- 选点报告inputs_unchanged=true，status=observed；lifecycle_effects_checked、
  source_program_checked、deployable均false。

新ID仅属于新AST；旧四项pending报告与其所有历史结果不变。下一步由独立
checker消费这些精确绑定和原始AST、保守检查完整受支持条件，再考虑解除
构造/生命周期义务，不能直接把原生trivial标志当作整个调用无写证书。

## 验证记录

GPT-5.6 Sol新增5项真实native回归，涵盖模板对象、精确constructor关联、
用户构造写全局、用户析构写全局的独立非trivial属性及观测边界。
首轮check.log在测试草稿冻结前加载旧断言，6个子例将模板实例record误认成
CXXRecordDecl而失败；真实节点为ClassTemplateSpecializationDecl，修正
测试而未放宽采集代码。完整最终日志为check-final.log，演示为demo.log。
最终make check为1095项全部通过（73.200秒，新插件启用，无跳过），
make demo和git diff --check通过；远端CI未核验。
