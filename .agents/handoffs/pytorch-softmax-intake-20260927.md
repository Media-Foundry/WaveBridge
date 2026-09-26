# 交接：新 softmax target 的冻结能力评估

- 日期、分支和基线：2026-09-27，wb03-source-ast，ee10c5d；开始时工作树干净。
- 用户目标：继续推进G2研究验收；中文回复，直接commit/push当前分支，无PR。
- 已完成：benchmarks/intake/pytorch-softmax-{protocol.md,harness.cu,result.json,
  config.example.json}；experiments/pytorch_softmax_intake.py与实验实录；10项
  driver测试、benchmarks/README.md、docs/status.md同步。
- 实际输入：PyTorch v2.5.1/a8d6afb511a69687bbb2b7e88a3cf67917e1697e未修改
  persistent softmax头文件加实例化harness。真实CUDA/Torch headers，仅声明
  外部warp_size，没有定义/返回值替换。不是生产SoftMax.cu或可执行baseline。
- 实际验证：冻结全部src/wavebridge为ee10c5d；Clang17 CUDA device-only
  sm80 full harness TU采集成功，518依赖，target/header实参精确绑定；float
  log2_elements=7非masked/nonlog实例8loops全unknown、0归约候选、1launch语法site。
  首拒绝bound_not_parameter_or_resolved_const；诊断为移位/条件常量表达式未支持。
- 工件：artifacts/wb-pytorch-softmax-KhwXBa/；attempt-01首次负结果保留。
  补强driver/config/protocol稳定性与actual header依赖绑定后attempt-02同结果，
  report SHA3a39162609eddcdd6a144749bc59b1e3fa895d7fe144cef7f7ef8d3db728d5cc。
- 全量验收：903项CPU测试65.559秒全部通过，无跳过；make demo与diff检查通过。
- 没有执行：GPU、数值测试、候选生成、性能、Polygeist/CKTI共同案例。
- 保证边界：PyTorch依赖树此前用于vLLM开发，不能算blind或严格独立谱系。
  新target首次冻结评估不等于G2通过；以后用于改进即开发反馈。已验收corpus仍1。
  analyzed只是driver运行状态，source_program_checked/deployable均false。
- 协作：GPT-5.6 Sol只读核查来源/早期暴露与统计范围；主代理实施driver/测试/Clang。
- 未提交/未推送：此文件创建时待commit/push，原始大工件按仓库规则本地保留。
- 下一项：通用受限整数常量求值增量（shift、条件及模板实参），需明确signed
  溢出、转换、短路与不支持范围，不能按WARP_SIZE名字硬编码；当前负结果不可改写。
- 阻塞：本轮无执行阻塞。完整语义/严格谱系隔离/强baseline差异仍未建立。
