# 交接：固定 logical32 module 回放

- 日期、分支和基线：2026-09-27，wb03-source-ast，c342c19；开始时工作树干净。
- 用户目标：继续推进，始终中文；直接commit并定期push当前分支，不创建PR。
- 已完成：experiments/module_replay.py 固定SHA与设备的HIP module回放；
  tests/test_module_replay.py CPU/mock与ctypes ABI回归；
  experiments/module-replay-20260927.md、docs/status.md 保存结果与边界。
- 实际验证：本机GPU0 W7900 PCI0000:53:00.0，HIP_VISIBLE_DEVICES=0，
  timeout60s调用上述入口，2331点通过冻结比较器；最大绝对误差
  1.1920928955078125e-7，输出与历史GPU结果字节一致。所有HIP API返回0。
  命令见实验记录。原始日志及报告：artifacts/wb-module-replay-pzJL4j/。
  完整make check共893项通过，66.209秒，无跳过；make demo及diff检查通过。
- 没有执行：native64、性能调优/计时、重新编译kernel、独立设备波宽探针。
- 保证边界：只运行固定historical logical32对象与固定3×777输入。信任HIP
  runtime/driver，不证明整核、实际FP误差律或全输入域；deployable=false。
  GPU_executed=false在失败时表示成功执行未建立，不保证GPU未开始执行。
  code object使用已验缓存bytes，不声称磁盘原路径全程不变。
- 协作：GPT-5.6 Sol实现脚本并在集成后只读复核；主代理补10项回归、核查
  ctypes ABI并执行实机。复核未发现阻断问题。
- 未提交/未推送：本文件创建时上述变更待全量验收后commit/push；实际提交见git。
- 下一步：针对已连接的真实binary执行，明确div lowering等尚未核验的算术
  前提；或优先回到独立谱系验收，不以本次有限回放宣布WB-03/适配全链通过。
- 阻塞：本次回放无阻塞；native64和全域语义义务仍未解除。
