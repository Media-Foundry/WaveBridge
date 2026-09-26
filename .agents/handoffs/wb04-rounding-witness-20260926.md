# 交接：两阶段归约的舍入见证

- 日期/分支/基线：2026-09-26，wb03-source-ast，d9201d4；开始工作区干净。
- 用户约定：中文、直接commit并推送当前分支，不建PR，不合并master。
- 完成：experiments/reduction_rounding_witness.py 固定路由的整数精确舍入诊断；
  tests/test_block_route_rounding.py 7项模型回归；实验说明和status同步。
  没有修改核心checker、baseline源、数值协议或部署许可。
- 结果：ncols34，x0=1，x1=x33=2^-12，其他0。局部平方精确；源width32总和
  0x3f800000，目标width64总和0x3f800001；贡献计数相同而DAG和舍入结果不同。
  全256线程有相同的跨宽度差异；各自配置内无lane结果分歧。
- 独立复核：GPT-5.6 Sol 编写C++ float快照实现，用g++ C++20 O0、
  -fno-fast-math -ffp-contract=off实际CPU编译执行，复核全部256线程。
  第一份/tmp版本只检查首logical group，后续版本明确每组重复shared loads并
  检查所有256线程；最终证据在artifacts/wb-rounding-witness-yHNsYH/。
- 验证：848项make check通过，66.726秒，匹配native插件启用；demo和diff
  检查通过。整数模型不依赖Python float舍入；独立C++是数值观察，不是证明。
- 原始工件：model-report.json SHA256
  6d66dcf255d78f6b934051a235f35ae1852a0a519ddd1b3efd4bbd22c5f6b5c8；
  independent.cpp SHA256 bd4a29ec9d15d8aec67bfdd228929bf73271d85ad6f1f42331a29c0456937cf6；
  run.log SHA256 db47953f169de8fabf5c451e8cad06cddc55373c8a4ac12b98765bded8b0081c。
  artifacts为本地忽略工件；可复现Python脚本和实验说明随Git推送。
- 未执行/局限：没有新GPU作业，没有fresh真实AST重放；路由显式提供。尚未
  检查实际shuffle、同步/FP语义、rsqrt和最终输出；不宣称超过冻结容限，
  不宣称native64错误、论文创新或全域误差界。
- 下一步：在保持冻结数值协议前提下处理归约误差及输出传播，或明确运算树
  保持的候选；禁止由局部值/贡献相同直接升级整核逐位等价。
