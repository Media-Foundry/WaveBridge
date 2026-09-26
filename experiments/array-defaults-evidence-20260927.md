# 默认实参效果与shuffle叶调用证据

2026-09-27，wb03-source-ast，基线edc0e51。无GPU、无生产AST重采。

```bash
PYTHONPATH=src:. python3 experiments/softmax_array_effects.py \
  --native artifacts/wb-native-template-OqD1PQ/native.json \
  --output artifacts/wb-array-defaults-Fpxw7d/replay.json \
  --use-scalar-operators --use-native-lifecycle --use-literal-defaults
```

固定native SHA256：
`a59c12247f796fe2034ba03ecc43782f77ac3942496b18a140ceacbb24c7ff45`。
输出SHA256：
`419bfbc1553852cc931e25903684fda8a0fdaa029b2ca36694892fba6bce44ee`。
inputs_unchanged=true，显式写入仍为7处，整体unknown。

## 默认实参

array_call_effects显式use_literal_defaults模式按同次完整AST的直接callee、
参数位置、形参类型与唯一默认initializer绑定CXXDefaultArgExpr。只支持
同类型int/unsigned int IntegerLiteral与bool literal，函数重声明、复杂
默认表达式、副作用或调用保留unknown。不从placeholder空子树推断无效果。
这个检查只解除默认实参，不检查callee、其他实参、数值范围或合法mask。

真实call0x30dce1d0的第3号参数0x30d89140，默认表达式0x30dce258，绑定
unsigned int literal 4294967295（0x309f4c28），求值无内存写入条件checked。
pending从两项降为一项CallExpr 0x30dce1d0；protected_storage_preserved
与deployable仍false。

GPT-5.6 Sol新增并复核5项真实Clang回归：unsigned/bool literal、旧模式、
有写入或调用的默认值、重声明继承、显式参数。完整1105项测试通过，75.392秒，
native启用、无跳过；make demo及git diff --check通过。日志在同一工件目录。

## 下一层真实调用路径（仅原始证据，尚未解除）

driver另保存固定新AST的原始节点摘录和builtin观测，不把它们当效果证明：

1. WARP_SHFL_XOR 0x30d89288，转发到__shfl_xor_sync 0x2e2c7bf8。
2. 后者调用builtin 0x2e2c7d78：__nvvm_shfl_sync_bfly_f32；调用0x2e2c8318，
   原生builtin ID1726（只在此编译器版本中有意义）。
3. 叶实参前三项加载标量形参，第四项为`((warpSize-width)<<8)|31`，不能
   简化成四个原样转发参数；相应const warpSize声明0x2dc920b0也保留。

本机IntrinsicsNVVM.td第4445行附近将shuffle族标记为
IntrInaccessibleMemOnly、IntrConvergent、IntrNoCallback，而不是IntrNoMem。
文件SHA256：`bbdd7571bbf61f348bf6e4daae7b50960d0dfa1985969f1bab96003c3da744f6`。

为核对实际lowering，新增只编译的探针：

```bash
/opt/AMD/aocc-compiler-5.1.0/bin/clang++ -x cuda -std=c++17 \
  --cuda-device-only --cuda-gpu-arch=sm_80 -nocudainc -nocudalib \
  -Xclang -target-feature -Xclang +ptx60 -S -emit-llvm -O0 \
  experiments/probes/shuffle_leaf.cu \
  -o artifacts/wb-array-defaults-Fpxw7d/shuffle_leaf.ll
```

初次未显式提供PTX feature的命令失败，要求ptx60及以上；同一失败已重放
保存在probe-without-ptx.log。加+ptx60后编译成功，日志probe-ptx60.log。
生成IR中叶声明为`llvm.nvvm.shfl.sync.bfly.f32`，属性为convergent、nocallback、
nounwind、`memory(inaccessiblemem: readwrite)`。探针wrapper本身在O0还有
局部alloca/store，不将leaf属性扩展为wrapper完全不写内存。

| 工件 | SHA256 |
| --- | --- |
| probe源码 | `f347aa3cd33029a0fb300aaa31d6f88d32141464adc32ee2bd9a50a3625a11bd` |
| probe IR | `e80272fa322a4b42237f8d33a210c120f3552120c2fa9daae5926db59fa9c641` |
| clang-17二进制 | `0aafa5b0712f974db5bbdd93a849b0b1e094bbb6314b8163278a22a90ce766b8` |

这是该工具链sm80/+ptx60探针的静态IR证据，不是完整kernel代码生成认证，
更不是实际设备执行。下一步应把“保持程序可访问存储”与“完全无内存效果”
分开，保留convergence/参与及有效执行前提，再独立检查两层wrapper及所有
实参效果；不得直接复用全局no_memory_write标签。远端CI未核验。
