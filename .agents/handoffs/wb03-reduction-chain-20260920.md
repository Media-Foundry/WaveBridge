# 累加器结构链恢复

- 日期2026-09-20；分支wb03-source-ast，基线377c2f0；中文、直接commit，不push。
- 新模块 `analysis/reduction_chain.py` 从同root AST重跑local_contribution与
  reduction_discovery，只接受完整预算下的唯一精确ID链。按block定义的形参顺序
  核对累加器位置，不假定value必须为第0参数；核对block/XOR宽度与列步长/线程数。
- `source.py`加入结构链报告及实现哈希。模块不接受人工component JSON，不根据
  函数名选择，不调用checker签发等价保证。
- 测试 `test_reduction_chain.py`通过真实Clang覆盖改名、合法参数换序、宽度错配、
  步长错配、未知consumer和预算耗尽；另注入重复block/XOR候选验证不择第一条。
  `make check`292项通过；Sol只读审查确认该有限范围内未发现实质错误接受。
- 实际源码命令：

```
PYTHONPATH=src python -m wavebridge.source benchmarks/cases/llama-rmsnorm/baseline/rmsnorm_logical32.hip.cpp --compiler /home/husrcf/Code/ProtBind/wavebridge/artifacts/toolchains/sdk-view-sx4rmd37/bin/hipcc --compiler-arg=--cuda-device-only --symbol rms_norm_f32_logical32 --int-bits 32 --output-dir artifacts/wb03-connected-reduction-01
```

- report.json SHA256：`a8dd4950eb1578c7fb9c3ddd7e0892a339f7e70e975fdc026f9d9ae1f167c276`
- ast.json SHA256：`f53b3fc8e686d871541c71b60aa1421f49c834b4bd8cf13470029ea462fe5a41`
- chain recovered：3段链接，width32、block256、offsets16/8/4/2/1；21条unresolved保留。
- 未运行GPU、不改变数值协议。shared实参对象/容量、alias、坐标和转换语义、实际
  launch、intrinsic、收敛及浮点数值仍未证明；本模块也不覆盖完整输出后缀。
- 下一步：把共享数组实参与block shared形参精确连接，并恢复其声明容量；之后
  才能把当前条件block-route检查的存储前提逐项绑定到源码。不把结构链当G3通过。
