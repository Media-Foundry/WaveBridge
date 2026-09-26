# 数组helper中空trivial对象自身构造/销毁效果

2026-09-27，wb03-source-ast，基线b541190；没有GPU执行或新源码采集。

```bash
PYTHONPATH=src:. python3 experiments/softmax_array_effects.py \
  --native artifacts/wb-native-template-OqD1PQ/native.json \
  --output artifacts/wb-array-lifecycle-PfkgIw/replay.json \
  --use-scalar-operators --use-native-lifecycle
```

新native SHA256固定为
`a59c12247f796fe2034ba03ecc43782f77ac3942496b18a140ceacbb24c7ff45`。
driver只在显式native模式使用这个工件及其新call ID，按原固定模板选择规则
定位保护变量；旧模式仍使用旧工件及旧ID，不拼接跨编译指针身份。

## 检查子集

array_call_effects.check新增可选native_payload。必须包含同一个root对象及
受支持的原生观测schema/语义，选中变量、直接compound、record、构造调用
和构造声明均重新精确绑定，重复或缺失保持unknown。

只支持自动变量直接执行的无参complete CXXConstructExpr。record必须是
完整、无字段无基类的empty trivial类型；defaultCtor与dtor标志都须trivial。
原生构造属性同时要求trivial/default，声明必须是implicit defaulted、
无初始化列表且只有空body/受支持属性的void()构造。析构声明存在时同样
检查implicit defaulted空定义；不存在时必须有needsImplicit/trivial证据，
不能把null当成无效果。已检查operator必须属于同一record，不能误连到基类
或同名类。只有以上条件全部满足才移除该变量与其唯一构造表达式的两项pending。

结论仅为对象自身受限构造/销毁不写其他存储，lifetime_history_checked=false。
原生前端仍属于可信基础；源执行有效、正常返回、对象存活且不同、数组访问
有界及无异步干扰仍是条件，不证明到达、存活区间、异常路径、浮点值或部署。
其他调用、默认实参和不支持效果继续保留，不由trivial标志整体豁免。

## 回归

GPT-5.6 Sol新增5项真实native组合回归：空template Max正例；用户构造/析构、
字段、基类负例；原生元数据缺失/重复/错绑/非trivial负例；旧无payload模式。
初次测试准备错绑定fixture时误要求聚合初始化产生constructor_calls，改为
从实际有构造调用的用户constructor样例获取错绑定目标，未放宽checker。
定向最终全部通过并冻结后再运行全量测试。完整日志为同目录check.log与
demo.log；远端CI未核验。

完整make check为1100项通过，75.366秒，新native插件启用，无跳过；make demo
及git diff --check通过。

## 固定新工件的实测结果

输出SHA256：
`02792540cbfc99ed1ca09ecd86565487a63694356e90208508c20a3ba7bee347`；
inputs_unchanged=true。call0x30de0078绑定float[2]数组0x30dddb58和保护
对象local_idx 0x30ddbeb0。对象r0x30dcdae0、record0x30d87bc8、构造
表达式0x30dcdb78与构造声明0x30d88228的受限效果条件checked。

显式写入仍为7处，Max operator独立检查保持通过。pending仅剩
CallExpr 0x30dce1d0（shuffle）和CXXDefaultArgExpr 0x30dce258。
status仍unknown，protected_storage_preserved=false。没有证明源执行有效、
完整历史保持、归约值或通信语义；接下来处理这两个效果义务再考虑接入历史。
