# 交接：双侧条件归约关系

- 日期、分支和基线：2026-09-26，wb03-source-ast，46614d5；开始时工作树干净。
- 用户目标：推进真实源码适配，中文回复，直接commit/push当前分支，不建PR。
- 已完成文件：verification/block_routes.py新增严格双侧模型比较；
  device_evidence.py新增fresh双侧AST编排；两份新测试、验证器说明、架构/状态同步。
- 算法边界：双方有限贡献计数均checked且block相同才按tid对应模型叶；有序
  add DAG由精确tuple共享intern，不依赖hash碰撞，不展开指数树；显式zero保留，
  不做结合律/交换律/零简化。不建存储操作DAG，不证明内存或同步等价。
- 验证：匹配AOCC17 native插件启用的make check最终783项通过（60.216秒）；
  make demo退出0，git diff --check通过。新增11项测试，含独立小形状展开树对照。
  首轮781项随后补充测试，以tests-final.log的783项为最终结果。
- 实际案例：PYTHONPATH=src python3 artifacts/wb-route-pair-OoaxAu/run.py，
  会话82172退出0，270.845秒；固定源/目标AST与两侧协议逐SHA核对，再重新恢复。
  两侧结构均evidence；模型贡献重数一致，256个输出位置加法树均不同，3468节点。
  report.json SHA256 aedc0193e81fe8c085f005f2ad117f479159ae37d3fb2713cc026080a881bf21。
- 工件：artifacts/wb-route-pair-OoaxAu/保存脚本、完整报告、输入和实现哈希、测试日志；
  本地忽略目录，不随Git上传。实现哈希前后稳定。
- 审查：既有GPT-5.6 Sol只读检查，未发现阻断性误放行；第二阶段重排与容量
  变化建议已补充测试。没有启动新的代理或GPU作业。
- 未执行：重新采集AST、GPU编译/运行、浮点数值验收、性能实验。
- 未建立：同tid局部累加值对应、全部width用途、输出数值关系、同步、源码到
  intrinsic/机器码、W7900 native64能力。树不同不等于实际FP值必定不同；
  树相同也不是IEEE等价。整体最多evidence，source_program_checked/deployable=false。
- 待提交：本轮两个实现、两个测试、三份文档及本交接，不提交大型工件。
- 下一步：从受限源码差异建立局部累加值对应，并解决width用途观察边界；
  不再以增加条件报告数量替代完整源目标关系门控。
