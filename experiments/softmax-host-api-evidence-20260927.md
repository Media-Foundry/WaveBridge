# softmax host API 来源核查

2026-09-27，基线 `4b6e2ab`，分支 `wb03-source-ast`。
本轮是固定依赖源码取证与AST调用观察，不是API数值证明或GPU实验。

## 先核实实现，再决定域

已只读取得PyTorch固定提交
`a8d6afb511a69687bbb2b7e88a3cf67917e1697e`的
[CUDAContext.cpp](https://github.com/pytorch/pytorch/blob/a8d6afb511a69687bbb2b7e88a3cf67917e1697e/aten/src/ATen/cuda/CUDAContext.cpp)。
内容SHA256：`41e17aca9ce11e2ff961f2877244899462efb7ecc0ca657891cdd7363b1a8d81`。
[同版本许可证](https://github.com/pytorch/pytorch/blob/a8d6afb511a69687bbb2b7e88a3cf67917e1697e/LICENSE)
SHA256：`47a26beb94e3f6b333a3677fc85d546f1fdfd2f0b3686c26d2fb5b10e0134165`。
两份原文保存在本地报告中，不在Git重新分发上游实现。

人工阅读固定源码可知：返回值取自当前设备属性字段；当前设备由c10取得，
属性经按设备缓存及call_once初始化，最终调用cudaGetDeviceProperties。
因此不能将此API实现解释为常量32，也不能将所有执行解释为无内存写入。
这条源码解读不等于证明当前运行二进制链接了该实现，更不自动确定设备。

## 当前拥有的是不同证据链

| 对象 | 已有依据 | 尚不能推出 |
| --- | --- | --- |
| 既有softmax CUDA sm80 TU | 精确调用、声明、自动局部变量直接初始化；同符号定义观察为空 | API返回值、实际运行库或当前设备 |
| 固定PyTorch实现 | 提交/文件/许可及内容哈希；人工核实依赖路径 | 与该TU实际可执行文件的跨TU语义和链接对应 |
| 历史W7900探针 | 独立HIP/gfx1100进程中host/device/ballot/shuffle/metadata一致的32 | softmax CUDA调用的返回域、运行时设备或launch值 |

W7900原始报告：`artifacts/wb01-20260920T074250Z-639474-321f6d/report.json`。
其历史结果不是本轮重新测量。softmax输入为何只有声明，已在冻结的
`benchmarks/intake/pytorch-softmax-protocol.md`披露；本轮不改写该协议。

## 可重放诊断

```bash
PYTHONPATH=src:. python3 experiments/softmax_host_api_evidence.py \
  --native artifacts/wb-native-template-OqD1PQ/native.json \
  --output artifacts/wb-softmax-host-api-KFKsOQ/report.json
```

脚本联网读取两个固定资源，先验SHA256验证后才使用；读取失败/哈希不匹配
不会产生成功报告。输出路径必须不存在。AST观察要求call、FunctionDecl、
局部int VarDecl唯一，变量直接由零参int调用初始化，callee声明按ID和类型
绑定。只按同mangledName记录可见定义，不将符号字符串当运行时链接证明。

真实会话57466正常退出，报告SHA256：
`601630306abaa91236b85411e21326178b73d0a095c86f6a5a443dfa0ecd6fdc`。
精确call `0x30d69260`、声明 `0x3020c788`、初始化变量 `0x30d691d8`；
符号 `_ZN2at4cuda9warp_sizeEv`，同符号可见定义列表为空。
root为 `7fc29b3984296fefb0534cec735a2b40e8b89e453530613112990e00a4b92970`。
输入/driver依赖前后哈希一致，结束后再次核对依赖一致。

5项真实Clang回归通过（0.038秒），覆盖同名不同namespace、已有定义仍不
升级运行时值、身份/initializer/预算错误，以及下载哈希与UTF-8边界。
GPT-5.6 Sol提供测试及只读复核；测试不联网、不执行GPU。
完整1197项通过（92.465秒，native启用、无跳过），demo/diff通过。
原始日志在 `artifacts/wb-softmax-host-api-KFKsOQ/{check,demo}.log`。

## 下一门槛

先明确实际执行视图：不能把CUDA sm80 AST与HIP W7900运行直接拼接。
对实际运行的kernel/host/API实现建立同一工具链与链接工件，再记录同一
进程的设备选择、API返回值及构造/launch路径。若改用HIP适配输入，应新建
带补丁和来源的工件，而不是将其冒充当前冻结CUDA TU。

在此之前，API返回域保持null；不存在可自动填入的32域。缓存初始化的
写入发生在minimum更新之前，不能据此否定已建立的更新后局部历史，但
也不能调用无写入checker把它消去。source/deploy、API纯度与运行时绑定
继续为false。本轮不把来源核查记为新的形式验证保证。
