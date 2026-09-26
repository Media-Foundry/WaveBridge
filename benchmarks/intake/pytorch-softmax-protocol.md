# PyTorch persistent softmax 首次冻结分析协议

冻结日期：2026-09-27；分析器提交 `ee10c5d6e0c8341e6c24d28521d40068114dfbdd`。
本协议在首次 Clang/关系分析执行前写入，不根据结果修改接受条件。

## 对象与暴露边界

- PyTorch v2.5.1，精确提交 `a8d6afb511a69687bbb2b7e88a3cf67917e1697e`，
  `aten/src/ATen/native/cuda/PersistentSoftmax.cuh`。
- 本地torch 2.5.1+cpu wheel已在早期vLLM工作中缓存并作为依赖使用；本次从
  固定上游提交获取的头文件与缓存SHA256一致：
  `12436933cae8c1e4096af342313070ce873eefad3d6a1637675ef780d1fdea1e`。
- 未发现此前针对`softmax_warp_forward`的分析/开发记录，但这不是blind
  holdout，也未证明严格代码谱系隔离；标记为已暴露依赖中的新target首次评估。
- 上游LICENSE为BSD三条款，摘要
  `47a26beb94e3f6b333a3677fc85d546f1fdfd2f0b3686c26d2fb5b10e0134165`；
  本地保留原文。本轮不在git重新分发该上游源码或第三方依赖。

## 固定输入与统计单位

输入是未修改头文件加公开的实例化harness，不是完整生产`SoftMax.cu`。
使用真实CUDA/Torch头文件，显式调用原`dispatch_softmax_forward`模板，
不手写或简化kernel/helper。仅补充`at::cuda::warp_size()`的声明（不提供
实现或固定返回值），避免引入本环境缺失的BLAS/sparse SDK头文件。
不替换CUDA intrinsic或线程索引实现。该环境适配单独披露。

预选一个实例：`softmax_warp_forward<float,float,float,7,false,false>`。
原dispatch会实例化多个长度；它们不算多个案例，也不根据恢复成功选择长度。
int_bits=32作为外部ABI假设。Clang CUDA device-only sm80只采集AST，不执行GPU，
不由此推断W7900能力。输入类型和实例选择不是人工关系oracle。

## 验收与拒绝

1. 冻结`src/wavebridge/**/*.py`哈希，运行前后校验；本轮不修改分析器。
2. 获取完整harness TU AST及同次依赖观测；编译缺依赖、超时、入口不唯一与
   语义不支持分别记录，不能混称“正确拒绝”。
3. 根据精确模板参数选择实例；对同一AST运行既有列循环恢复、归约发现和
   launch发现，不按函数名提供关系模板，不读取人工oracle。
4. 记录全部循环及拒绝原因、归约候选、launch绑定。analyzed只表示分析执行，
   不能升级source_program_checked、适配通过或deployable。
5. 没有数值reference、正确目标baseline或独立正确性标签，本轮不填有效接受率、
   错误放行率及性能，也不新增完备corpus案例数。
6. 若结果暴露能力缺口，原始结果原样保留；之后用于改进即成为开发反馈输入。
   不通过更换版本/选实例/写简化kernel获得“通过”。

来源：[固定头文件](https://github.com/pytorch/pytorch/blob/a8d6afb511a69687bbb2b7e88a3cf67917e1697e/aten/src/ATen/native/cuda/PersistentSoftmax.cuh)、
[固定许可证](https://github.com/pytorch/pytorch/blob/a8d6afb511a69687bbb2b7e88a3cf67917e1697e/LICENSE)。
