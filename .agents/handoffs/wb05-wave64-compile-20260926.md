# 交接：wave64 编译观察

- 日期、分支和基线：2026-09-26，wb03-source-ast，411c775；开始时工作树干净。
- 用户目标：持续推进真实源码适配，中文回复，直接commit并推送当前分支，不建PR。
- 已完成：docs/status.md与experiments/wave64-compile-observation-20260926.md记录
  gfx1100默认/实验wave64编译、实际bundle成员提取与元数据检查。
- 实际验证：两次device-only编译退出0；提取成员readobj退出0，波宽分别32/64，
  与链接临时产物SHA一致；git diff --check通过。工具、命令和报告SHA见实验记录。
- 工件：artifacts/wb-wave64-compile-gloEbQ/，忽略目录，仅本地保存。
- 未执行：GPU probe、候选GPU运行、数值/性能评测、完整CPU测试。
- 局限：HIP develop文档注明RDNA实验选项不受运行时支持，不将编译成功解释为
  本机设备能力。依赖清单未生成，闭包unknown；首次readobj直接读取bundle失败
  的报告保留。runtime_verified=false、deployable=false。
- 协作：既有Sol代理只读审查探测边界，没有修改文件或启动GPU。
- 本次待提交：上述两份文档及本交接；不提交大型工件，不修改默认probe协议。
- 下一步：继续离线源目标关系与宽度用途边界检查，保留logical32正确基线；
  native64执行需独立确认支持的设备/运行时，不把W7900实验模式设为必须成功。
