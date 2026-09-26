# 交接：局部平方累计与归约误差组合

- 日期/分支/基线：2026-09-27，wb03-source-ast，d40fb08；开始工作区干净。
- 用户约定：中文、直接commit并推送当前分支，不建PR、不合并master。
- 完成：block_roundoff.compare_sum_squares按明确t+kB列分配、零初值、FMA或
  separate模式推导各线程局部误差和叶上界，再与该侧route误差组合。旧API
  不变；新接口不要求两侧computed leaves相同。保留fresh per-side checks，
  丢弃原route comparison不适用的共同computed-leaf假设，避免报告混淆。
- 数学：proof-writer技能用于在PROOF_PACKAGE.md追加完整条件命题及证明，
  GPT-5.6 Sol只读复核无阻断。局部r/b/M与route r/A组合为
  c=a+r(1+a)、e=(1+r)b+A，相对共同精确平方和Q；双侧再相加。
- 验证：新增6项测试；FMA/separate四种配对共972组小域用独立有理舍入模拟
  检查。860项完整make check通过，63.913秒，匹配native插件启用；demo、
  diff检查通过。测试覆盖旧1ULP见证、单列/零域、实际尺寸、错误路由及
  输入域/局部迭代预算/有限范围拒绝。
- 模型重放：ncols1023、B256、输入幅值2，255线程4次、1线程3次。FMA leaf
  upper约16.0000023842，separate约16.0000033379；从实际舍入递推取界，不
  将数学16直接当成computed accumulator界。差值界精确分数见原始报告。
- 工件：artifacts/wb-sumsquares-bound-TpuLbo/run.py、report.json、check.log、demo.log；
  report SHA256 e1b185f05a555c688222361b48cea1777202d7e8bba104778e2e989009b2e4aa。
  工件本地忽略，代码/测试/证明/文档推送。
- 局限：没有GPU作业或fresh真实AST；实际源码索引/输入配对、FMA模式与
  误差律适用性仍是外部前提。numeric_contract_checked/deployable仍false。
  未更改冻结tolerance、baseline或设备模式，未声明研究新颖性成立。
- 下一步：处理除法、epsilon、rsqrt与输出乘法的误差传播，并将模型条件与
  实际源码/工具链证据相连；不得把本次平方和界直接当完整RMSNorm验收。
