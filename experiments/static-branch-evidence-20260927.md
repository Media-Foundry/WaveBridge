# 静态布尔分支选择证据

2026-09-27，分支wb03-source-ast，基线a4c8ea7。本轮无GPU、无生产AST重采。

```bash
PYTHONPATH=src python3 -m experiments.softmax_exit_guards \
  --native artifacts/wb-column-builtins-twz82w/native.json \
  --recovery artifacts/wb-loop-calls-SIr4BJ/all-calls.json \
  --work-preservation --static-branches --int-bits 32 \
  --output artifacts/wb-static-branches-O9LPyQ/replay.json
```

新增模式从原始AST重新核验完整条件求值，只接受bool literal、已核验的bool
模板替换、括号与逻辑非。动态条件或不支持表达式不当作false；仍按原路径
检查条件与两臂。带初始化/条件变量、constexpr/consteval的if不参与静态选择。
默认模式保持不变，新模式schema为
`loop-exit-work-preservation-with-static-branches/v1`。

选择记录包含原始条件AST、布尔值、所选臂及相对唯一loop的child路径；
不改写AST，不从案例名称或driver配置猜测模板值。未消费协议仍阻止成功。

固定输入SHA256：

- native：`317b1a438bc13845cf76b5aa7461db4db2081b402c457a85c4160fdd7257c027`
- recovery：`31a6570762225ea247f24b799be28ebd51f3dab13e562e32cccb8e305d764f67`
- 输出：`dd11cdbe6c6230861a468d0bc2835f6274674e423e21052435bbede089c96999`

回放inputs_unchanged=true。外层在路径[4,1]核验false并选择none，跳过不可达
log调用；随后以nested_loop_in_body返回unknown，未消费调用成功记录。
内层在[4,1,1,0]核验false并选择else，work条件checked；唯一完整调用
0x19550c18重新检查通过，其外部builtin无写/正常返回假设仍未验证。
部分静态选择不能提升unknown父报告；可达嵌套loop仍不在本检查器支持范围。

这不建立完整迭代域、溢出/覆盖、浮点等价或源程序有效性。无别名、有效源程序、
无异步干扰等前提继续保留。历史6/8循环恢复没有提升，不构成新holdout或GPU证据。

实际验证：

```bash
WB_NATIVE_CAPTURE_PLUGIN=/home/husrcf/Code/ProtBind/wavebridge/artifacts/wb-native-builtins-JR99CL/libwavebridge_capture_plugin.so \
WB_NATIVE_CAPTURE_COMPILER=/opt/AMD/aocc-compiler-5.1.0/bin/clang++ \
make check
make demo
git diff --check
```

完整1053项测试通过，71.478秒，无跳过；demo/diff通过。日志保存在
artifacts/wb-static-branches-O9LPyQ/{check,demo}.log。
GPT-5.6 Sol新增5项真实Clang回归并只读复核：模板true/false、字面量/括号/非、
动态及有副作用条件、不可达/可达嵌套循环、未消费协议及非法模式参数。
测试从Clang真实TemplateArgument读到true=-1、false=0，按精确值选实例；
生产静态条件判断读取的是CXXBoolLiteralExpr的严格布尔值，不依赖这一编码。
远端CI未核验。
