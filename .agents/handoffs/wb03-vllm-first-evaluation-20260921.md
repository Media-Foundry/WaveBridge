# vLLM第二仓库首次源码评估

- 日期/基线/分支：2026-09-21，04c01e4，wb03-source-ast；中文、直接commit/push。
- 用户批准继续独立谱系与依赖绑定；本轮不扩getter或RMSNorm专用支持，不GPU。
- 固定来源：vllm-project/vllm v0.6.6，commit f49777ba62b4926d0f8c100ab06edb03c5c10098。
  下载完整tar，不改任何上游文件；LICENSE为Apache-2.0。源/许可/archive哈希
  见benchmarks/intake/vllm-rmsnorm.json。人工源筛查后选定，不声称随机盲测；
  仓库不同，完整历史共同祖先尚未审计。1个候选，不把template/实例算多条谱系。
- 工件：artifacts/wb03-vllm-holdout-GqLQJo，attempt-01至06报告及analyze*.py，
  包含完整命令、stderr、filtered AST、源码/compiler/实现/runner/intake哈希。
  先登记并冻结分析器，再运行。所有src实现hash每次运行前后及最终复核一致。
- 环境失败1–4：缺crt头；缺curand头；本机Torch头不兼容；CPU2.5.1 wheel缺CUDA
  生成配置头。它们不算分析器语义拒绝。没有升级或覆盖本机软件。
- 独立下载torch2.5.1+cpu wheel（174.6MB）仅解压torch/include；上游build
  requirements固定2.5.1。CUDA runtime/nvcc12.1、cuRAND10.3、CCCL12.1及
  libcudacxx1.9来自已有隔离工具链。显式定义C10_CUDA_NO_CMAKE_CONFIGURE_FILE
  使用上游CUDAMacros.h条件跳过缺失生成头；这是解析配置，不是官方完整构建。
- 最终命令：`PYTHONPATH=src python3 artifacts/wb03-vllm-holdout-GqLQJo/analyze-06.py`。
  Clang17.0.6、--cuda-device-only --cuda-gpu-arch=sm_80、-fsyntax-only，编译退出0，
  17.30196秒；不是GPU执行或机器码生成。host-only attempt05也collected，但
  其mangled name为device_stub，必须与device视图区分。
- device最终报告SHA256：f75e566c7443bd4ab69acd5a3e7c5c89af80d75c30f3892d779dfaf81f2a38f7。
  3个filtered根，rms_norm_kernel有1模板节点、1模板体及3实例；模板节点不能作
  recover(FunctionDecl)输入，保留function_unique_body_not_found诊断。
  float/Half/BFloat16各2循环均unknown，首因unsupported_value_wrapper：
  直接threadIdx.x的unsigned PseudoObject经IntegralCast初始化int induction。
  不将其改写为const tid，也未增加支持规则。后续blockDim.x步长/CUB未实际评估。
- 本轮验证：实际host/device语法编译和冻结分析器运行、JSON/哈希检查；未改src，
  未新跑完整CPU测试、GPU或数值。已有457测试结果不能称本轮重跑。
- tracked：intake冻结登记、协议、结果索引、benchmarks README纠正旧空语料描述、
  status与交接；上游archive/wheel/raw AST仍本地忽略，不是完整公开复现包。
- Sol只读依赖审查：collect当前只绑定直接source和wrapper；建议同次AST加
  -MD -MF（不是-MMD）取得含系统头depfile，严格解析并绑定路径/文件hash；
  保存同参数-### raw trace，索引真实cc1 executable、target/resource-dir和
  bitcode。HIP实际wrapper为Python脚本，clang-23与OCKL/OCML未被当前报告绑定。
  记录观测后内容及source前后稳定性，不声称并发修改完全排除或冻结快照。
- 下一步：实现上述最小依赖manifest及失败传播/头文件变更回归。vLLM本例已经
  暴露给开发者；任何由它驱动的支持扩展需作为development反馈，再选新未见
  案例验收。WB-03仍未通过独立谱系迁移验收，总研究目标仍未完成。
