# 动态 shared 的单点隔离诊断

日期：2026-09-20；基线 `24b93d3`。这是人工诊断，不是自动候选、第二个生产
案例或已验证的移植。原 adapter、完整输入失败与原 IR 均不覆盖。

## 唯一输入变化

在独占 `artifacts/polygeist-static-shared-huVSt0/adapter.cu` 创建原 adapter
的诊断副本，`diff -u` 确认只有以下一行变化：

```diff
-  extern __shared__ float shared_sum[];
+  __shared__ float shared_sum[32];
```

原源 SHA-256：`9bd5e5d8bc9eb175b9b05f200a3db9840da013991d7f0e772197c6e765ece7bf`。
诊断源 SHA-256：`f29dd62b5c44e2330e4376ea306c5f36f5bb195612fac0bd98e574ed7489c739`。
launch 仍请求128字节动态shared，因此此副本还额外声明128字节静态shared；
不得将其用于等资源性能对照，也没有宣称GPU语义等价。目的仅是隔离不完整
数组声明的前端处理，计算、shuffle、域和launch均不另改。

## 实际运行

与原 adapter 相同的 CUDA11.8/GCC11 头、cgeist、resource-dir、sm_70 和
全函数选择，分别运行默认 O0 与 `--cuda-lower`。完整命令、工具/runner/hash
及原始诊断保存在下面的 report.json。两次退出0，只记 emitted_unverified_ir。

| 工件 | SHA-256 |
| --- | --- |
| `artifacts/polygeist-frontend-uxwve8ha/report.json`（默认） | `e6bf2266d0fbc47675c72f1e3e716dfa9499dcd29923aeaf96a5dc9bf5e0cdee` |
| `artifacts/polygeist-frontend-nzrj77xy/report.json`（lowering） | `f5f864b613b2e1c2ac9bc037cc374ceb1a30116ee125c3a16be169ca3776ff98` |
| `artifacts/polygeist-frontend-nzrj77xy/output.mlir` | `b958c1a3b21d4d21b1cebe037aa1d858df04b7ef616e59a0939d86fbe822f501` |

lowering IR第52行变为 `memref.alloca() : memref<32xf32>`；82/90行原有
shared写/读仍为group/lane索引0～7。因此此前显式容量1的矛盾不再出现。
此观察只覆盖容量与这两个索引，不证明同步、路由、浮点或整个输出正确。

第70/100行仍调用外部 `__nvvm_shfl_sync_bfly_f32`，第124行仍是无定义声明；
stderr仍警告无法发射该builtin。静态shared声明不能解决这个独立边界。
固定前端 `CGCall.cc:1537` 的警告分支之后继续普通callee处理，不能将警告
等同于工具已经拒绝输出，也不能将外部声明等同于正确NVVM/ROCm映射。

## 下一项证据

Sol只读定位、主代理复核固定源码后的容量路径：

- `tools/cgeist/Lib/clang-mlir.cc:5606–5634`：非ConstantArrayType的数组长度
  保持-1；`VisitVarDecl:942`因shared属性指定memory space 5。
- 同文件 `createAllocOp:530–561`：VariableArrayType可计算运行时长度；
  其余未知首维在556–557行回退为1，再创建alloca。
- `lib/polygeist/Passes/ParallelLower.cpp:599–611`：将space5分配移到block
  scope并去除space，但保留shape，没有从launch恢复动态shared容量。

因此本例的容量1可追溯至未知数组长度fallback；并非只根据IR外观猜测。
shuffle方面，固定前端GPU调用处理能产生barrier操作，但本次shuffle仍走
普通外部函数调用。现有GPU/NVVM操作的lowering规则不自动证明普通外部
`func.call`获得相同映射；尚未实际检查最终LLVM/机器码或链接结果。

分别追踪动态shared到分配的规则、shuffle外部调用到后端的处理。只有完成
后端或具体变换检查后，才能评价其自动原生适配能力；不能从此前端诊断推断
所有Polygeist版本或其方法不支持此模式。未改上游工具源码，未执行GPU、
coarsening、数值或性能实验。G1仍未通过。
