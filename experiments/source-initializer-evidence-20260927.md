# 固定softmax可变local_idx的初始化时值域

2026-09-27，分支wb03-source-ast，基线710447d。无GPU、无生产AST重采。

真实输入中0x19546950为自动可变int local_idx。其初始化含IntegralCast，
内部为CUDA属性PseudoObjectExpr和静态getter，最终指向精确builtin声明
0x163f7438。这里的名称只用于描述，checker按声明身份与真实body检查，不按
threadIdx或local_idx名字赋予坐标含义。

旧initializer_evidence入口要求const，因而不把这个可变声明当作稳定起点。
本轮没有放宽该门槛，而是在既有initializer_domain中增加fresh源码入口，
结论严格限于初始化完成时，value_preserved_to_use=false。

```bash
PYTHONPATH=src python3 -m experiments.softmax_initializer \
  --native artifacts/wb-column-builtins-twz82w/native.json \
  --protocol experiments/softmax-initializer-protocol-20260927.json \
  --output artifacts/wb-source-initializer-vkxhkA/replay.json
```

native SHA256：
`317b1a438bc13845cf76b5aa7461db4db2081b402c457a85c4160fdd7257c027`。
外部协议SHA256：
`56e4d92bae9457348061f413666c21cfdb3fda15bbea4ed1da7d0e508c0ac169`。
协议将精确leaf声明的返回范围设为[0,31]并提供signed/unsigned int32 ABI。
这是未与launch连接的外部假设，不是从源码恢复了真实线程范围；协议没有
声称builtin纯度或设备执行，initializer完整effects也不由新入口保证。

实际验证：

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_source_initializer_domain_clang.py' -v
WB_NATIVE_CAPTURE_PLUGIN=/home/husrcf/Code/ProtBind/wavebridge/artifacts/wb-native-builtins-JR99CL/libwavebridge_capture_plugin.so \
WB_NATIVE_CAPTURE_COMPILER=/opt/AMD/aocc-compiler-5.1.0/bin/clang++ \
make check
make demo
git diff --check
```

新增5项真实Clang回归通过（0.059秒），GPT-5.6 Sol实现测试及只读复核。
覆盖mutable/const初始化、unsigned到int的非值保持转换、static/TLS/reference、
间接调用/带副作用逗号表达式、错误leaf及预算；另在真实AST副本上注入重复
声明ID验证拒绝，不将该fixture称为编译器产生的原生AST。远端CI未核验。

完整1073项测试通过（73.302秒，native启用，无跳过），demo/diff通过。
固定回放inputs_unchanged=true，输出SHA256：
`67801438dbfbd9baa97a5caba15a96b4c82e793fbb863b0f96d894c69068c180`。
初始化表达式0x19546b48重新连接getter 0x163f6230 → leaf 0x163f7438。
在显式[0,31] leaf域下，getter int→unsigned int以及初始化unsigned int→int
转换均checked，result_interval=[0,31]。receiver观测为observed，但完整
初始化效果未证明。value_preserved_to_use仍false，未修改循环域协议，也
未把此前local_idx外部区间升级为已证明的loop-entry域。
