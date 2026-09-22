# 交接：自动对象初始化组合检查

- 日期：2026-09-23；分支 `wb03-source-ast`；基线
  `01dbdb0b62a2241ec2a224ee9e2ccd90501d30ba`，开始时工作树干净。
- 用户约定：中文回复，验收后直接 commit/push 当前分支，不创建 PR，不合并 master。
- Sol 子代理实现 `verification/object_initialization.py`；主代理补真实原生测试、
  审阅、完整 TU 采集/检查及文档。没有启动 GPU。

## 实现与范围

从同次原生 envelope 的唯一自动 VarDecl 关联直接构造和可选清理 wrapper；
检查完整身份、类型、作用域、存储期和声明形状。存在 wrapper 时必须有同上下文
正面记录，精确绑定子表达式，严格 false 副作用标志和整数0辅助对象数。
计数不是析构次数；JSON 自带 flag 与原生观察冲突不能通过。

fresh 组合参数效果、构造器效果及字段域，不消费外部成功报告。checked 只描述
有效源码、匹配 ABI、外部输入域以及正常返回前提下的初始化完成时点。
此前别名、后续值保持/逃逸、析构、异常展开、动态调用历史和 launch 均未建立。
source_program_checked/deployable 始终 false。没有将旧子报告的未知项回写为通过。

实现冻结 SHA-256：
`92cbdb2dde218f60bb94e9589e358f05e353f9eeb0dbcc60ab57ed2d508c7007`。

## 实际本地验收

以下命令在仓库根目录运行；native 插件与 AOCC Clang17 匹配：

```bash
export WB_NATIVE_CAPTURE_PLUGIN="$PWD/artifacts/capture-plugin-cleanups-gYQ3gz/libwavebridge_capture_plugin.so"
export WB_NATIVE_CAPTURE_COMPILER=/opt/AMD/aocc-compiler-5.1.0/bin/clang++
make check
PYTHONPATH=src python3 -m unittest discover -s tests -p '*clang*.py'
make demo
```

611 项 CPU、144 项 Clang 专项及 demo 通过。新增5个测试方法覆盖普通直接初始化、
标量临时量、嵌套块正例，以及 static/TLS/引用/volatile/属性/lambda/析构临时量、
清理观察缺失或冲突、声明身份/形状改变、缺域、预算和输入不变性。
真实前端产生 AST；元数据负例是在该 AST 上作单点修改，不是新 GPU 结果。
日志位于 `artifacts/wb-vllm-cleanup-native-a1pI0L/{check-tests,clang-tests,demo}.log`。

## 固定 vLLM 完整 TU 重采集

源码固定 `f49777ba62b4926d0f8c100ab06edb03c5c10098` 的
`csrc/layernorm_kernels.cu`，SHA-256
`57d5d4e2912e0661d57a0eab4a837ea7a8cab794b7e4cf10b7d5f42dd31ef2d8`。
复用旧 `artifacts/wb03-vllm-holdout-GqLQJo/attempt-06.json` 的编译输入，
其 SHA-256 为 `f75e566c7443bd4ab69acd5a3e7c5c89af80d75c30f3892d779dfaf81f2a38f7`。
仍是既有 nvptx64-nvidia-cuda device-only 视图，不是新增代码谱系或通用 CUDA 支持。

```bash
PYTHONPATH=src python3 artifacts/wb-vllm-cleanup-native-a1pI0L/collect.py
PYTHONPATH=src python3 artifacts/wb-vllm-cleanup-native-a1pI0L/check.py
```

采集及保存/哈希耗时199.55秒：296条 capture、7656条 cleanup 观察、5456项依赖。
AST 保存为同目录 `ast.json`，SHA-256
`f80432e744686fdc1390308073a3cd7e1b1d1ba5afd065198dcc292ab21ee9ee`；
`collection.json` SHA-256
`2a26ed80837c026878d993a4148d2407f932da329a0ae096782a1cfe6b9e6b29`。
采集期间四个前端实现文件哈希不变。

新 VarDecl ID `0x373701f0`，wrapper `0x37370e80`，构造式 `0x37370e38`。
诊断脚本以固定位置选择案例后把精确 ID 交给 checker；名称不赋予检查语义。
没有把旧 AST 的 ID/清理记录拼入新工件。

完整 TU 的 fresh 初始化组合检查为 checked，completion=conditional；外部域及
ABI 前提下 x∈[1,1024]、y=z=1。耗时424.998秒，75个 Python 实现文件前后哈希
一致。结果 `initialization.json` SHA-256：
`dd4cf4844f66783bdab649ad082fcadb0890355bd51aaf1ecd4a8eb7eb8b37ee`。
字段名仅供显示，实际按 FieldDecl ID 和参数位置关联，不推断 launch 轴语义。

插件 SHA-256：`8b56a3b0e4241a59408d4d796da0e3ce7e931e7c8448db2630c1f0d876c2a3db`。
源文件 `compiler/frontend/native/capture_plugin.cpp` SHA-256：
`2c53688068ae9e30d8968efe84317e4f5fd828d9789908d751588ce5fe97e1bb`。

## 尚未执行或建立

没有 GPU 数值/性能执行、代码生成或部署。外部 hidden_size∈[1,4096] 与
int32/unsigned32 ABI 不是本轮自动推断或硬件探测结果。
下一项是限定路径上的初始化后写入/逃逸与复制点值保持；不能把本轮字段域直接
转移到 lambda 复制或 GPU launch。完整 TU 多次哈希的成本仍待处理。
