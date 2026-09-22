# 交接：全引用捕获链的条件对象身份

- 日期/分支/基线：2026-09-23，`wb03-source-ast`，`29c74fe`。
- 用户目标：继续完成真实源码关系链，中文回复；验收后直接提交推送，无 PR。
- 完成：`capture_source_check.py`（Sol 实现，主代理审阅）；真实 native fixture
  与 9 项回归（主代理）；检查协议与状态同步。
- 实际验收：设置 `WB_NATIVE_CAPTURE_PLUGIN` 为
  `artifacts/capture-plugin-VKdLhn/libwavebridge_capture_plugin.so` 的绝对路径，
  `WB_NATIVE_CAPTURE_COMPILER=/opt/AMD/aocc-compiler-5.1.0/bin/clang++`，
  `make check` 583 项无跳过、`make demo`、
  `PYTHONPATH=src python3 -m unittest discover -s tests -p '*clang*.py'` 116 项通过。
- 保证范围：同 ASTContext 的普通自动非引用对象、每层正面存在的 by_reference
  捕获边，在外部源存活初始化、闭包来源、同动态 activation、源有效性前提下，
  条件证明 copy 实参 lvalue 的对象身份。原生元数据仍为可信前端；引用来源
  evidence_reference 未核实，不证明无写历史、调用发生、launch、GPU 或部署。
- 明确未知：按值层、引用变量、static/TLS、init-capture、generic/template、
  作用域/路径/ID 歧义、协议缺失或非严格布尔值不能 checked。按值层不代表原程序错误。
- 下一项：先核对完整生产 TU 上的条件身份链；随后把同一对象从原始构造到
  复制之间的无写义务独立建立，不能仅因为身份相同就搬用构造字段域。
- 未执行：GPU、数值或性能实验；没有把外部生命周期假设改写为自动证明。
- 完整 TU 重放：`PYTHONPATH=src python3 artifacts/wb-capture-source-x9KJTH/run.py`。
  输入为上一轮完整 `artifacts/wb-vllm-native-Rw42Hh/ast.json`，SHA256
  `c4642860faadf8920de29c3e79ca8dc984cd88af0e5ede7ce3f6de18b02c4d45`；原生
  root 哈希 `60cbcdf189f1c27b70504d223ae1512bb073ff129af87995a8c1855da4a0f2c4`。
  复制 `0x38e56348`、词法源 `0x38e43f10`，fresh 核对链
  `0x38e671e0 → 0x38e58010`，两层 by_reference，结果条件 checked。
  报告 `artifacts/wb-capture-source-x9KJTH/report.json`，SHA256
  `d2f24cfb76dc1b85fdb3e508f2ea5b7564ccd68c51986c69108a6a03e06cb8a8`。
  计时 172.62 秒（不含起始输入文件哈希核对），七个实现文件前后哈希一致；
  checker SHA256 `d516ba48c9613f13cda4ba006cc7393e3793cc059251b5c0510eea2b530e7445`。
  外部协议四项布尔前提均明确为诊断假设，`protocol_evidence_verified=false`、
  `identity_completion.external_evidence_verified=false`，未核实真实生命周期。
  旧复制子报告的 source_object_identity 仍 not_established，不回写覆盖。
  这是同一开发输入的条件检查，不是新增 holdout 或无条件源/目标等价证明。
- 提交状态：随本轮验收提交推送；远端 CI 以实际提交工作流为准。
