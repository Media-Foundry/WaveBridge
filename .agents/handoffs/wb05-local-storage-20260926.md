# 交接：局部贡献声明求值的保守性修复

- 日期、分支、基线：2026-09-26，wb03-source-ast，f880aea；开始时工作树干净。
- 目标：中文回复，继续源码适配；用户授权直接commit及push当前分支，不建PR。
- 背景：开始局部累加值对应检查前，发现两个sum_of_squares标签可能源自不正确
  的初始化执行次数模型，先处理该前提，不直接增加成对成功结论。
- 独立复现：真实Clang AST中，static/thread_local accumulator与loop value、
  消费前VLA维度写partial均被旧实现recovered。CPU输入[1,2]连续调用两次，
  普通自动版本5/5，两个持久accumulator版本5/10，两个持久load版本2/2，
  VLA维度赋7版本7/7。无未定义行为或GPU执行作为论据。
- 实现：analysis/local_contribution.py限定scalar自动存储期/无TLS/无未知Attr；
  消费前array需精确float正固定extent或extern不完整array，无init/求值children，
  最多一个childless CUDASharedAttr。类型与children同时核对，不依赖VLA维度
  一定出现在inner中。普通extern声明无局部初始化，继续保留外部分配unknown。
- 验证：make check最终789项通过，61.060秒，AOCC17匹配native插件启用；
  make demo退出0，git diff --check通过。新增6项方法：存储/属性合成AST、
  五变体真实Clang、实际CPU连续调用、source.run→normalization无mock组合负例。
- 失败记录：首次全测789项中一个旧extern float[]正例失败，说明初版拒绝过宽；
  修正为允许无求值的extern声明后完整重跑，不删除tests.log旧失败。
- 正例：固定既有HIP源/width64目标AST逐SHA核验，fresh normalization恢复及其
  local_contribution均recovered，动态shared路径保留；不是重新编译源码。
- 工件：artifacts/wb-local-storage-JIGuU5/，本地忽略目录不上传大型工件。
  reproduce.py before.json/after-final.json；positive.py positive-final.json；
  tests-final.log、demo-final.log、CPU原始命令/版本/输出、源和实现哈希。
- 关键SHA：before.json=4b28c8b43b411382701c0852c3909dcb7dc79c920782a76bc5f9f41f940dc20f；
  after-final.json=27135c0d79155e1ac80ff87f53b3a7be4d7051a99e29135172854e7760c00194；
  positive-final.json=6553483ae63f3deff24f564bc9a3bec71350bfcffb0ce94a1001815723cbc658；
  local_contribution.py=5291bd405eac9cbd087e774b31efd7ce0927f7c9ddae3f4633366ddfb8459fcd。
- 代理：既有GPT-5.6 Sol只读复核，未发现阻断性误放行；重复shared属性建议已
  拒绝，固定shared形状与普通extern支持边界已补测试/说明。
- 未执行/未建立：GPU、重新HIP编译、跨源码局部值对应、数值/性能实验；
  declaration_evaluation不代表可达性、alias/FP/整核有效性，所有checked/deployable
  仍false。反例只证明C++源码恢复问题，不证明历史RMSNorm GPU结果错误。
- 待提交：实现、3份测试修改、新C++ fixture、分析/状态文档与本交接。
- 下一步：在此基础上比较局部运算、输入角色与有序递推，绑定源码差异及宽度
  用途；不要把相同operation标签或相同贡献集合写成源目标叶值已经等价。
