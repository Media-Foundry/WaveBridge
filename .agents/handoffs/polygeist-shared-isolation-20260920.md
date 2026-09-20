# shared 单点诊断交接

- 日期2026-09-20，分支 `wb03-source-ast`，基线 `24b93d3`；开始工作区干净。
- 中文回复，直接本地commit，不创建PR、不推送。
- 主代理在独占artifacts副本仅改shared声明，diff确认单行变化，实际运行默认
  与cuda-lower。结果、全部工件/哈希和边界见
  `research/polygeist-static-shared-diagnostic.md`。
- 原adapter和工具实现均未修改；不完整数组变为定长后容量矛盾消失，shuffle
  警告不变。不是完整正确性证明或新的生产语料。
- Sol只读定位未知数组长度fallback；主代理复核数组类型转换、createAllocOp
  和ParallelLower代码，与两次IR对照一致。具体路径已写入诊断文档。
- 验收：真实cgeist两次退出0、手工检查IR容量和访问、源/report/IR哈希、
  `git diff --check`。只改研究记录，未重跑已有280项测试。
- 未执行GPU、数值、性能或完整后端。下一步核对动态数组及shuffle的具体
  lowering边界；保留原失败，不以人工副本取代原自动化要求。整体目标未完成。
