# 交接：冻结基线构建绑定与数值重放

- 日期/分支/基线：2026-09-26，wb03-source-ast，d292600；开始工作区干净。
- 用户约定：中文；直接 commit，推送当前分支，不创建 PR 或合并 master。
- 完成：llama-rmsnorm/runner.py 将原 O2 命令、工作目录、固定输入文件和实际
  binary 绑定；编译前/执行前/执行后核对哈希，变化阻止后续数值比较。缺/空
  binary 单独 invalid_binary。新增 tests/test_rmsnorm_build_binding.py，更新
  案例 README、docs/status.md。未修改源 kernel、协议、reference 或容限。
- 验证：841 项 make check 通过，64.003 秒，匹配 native 插件启用；demo、
  diff 检查通过。6 项新增 mock 方法由 GPT-5.6 Sol 协作实现，全部冻结后全测。
- 使用 run-experiment 技能：先用 rocm-smi 核对 GPU 空闲（W7900，GPU0 VRAM
  26734592 bytes，利用率0，无 KFD PIDs），再新探针，最后既有基线。
  未启动远端实验或外部通知。
- 失败记录：普通 hipcc 缺开发链接名，wb01-20260926T153905Z-2-f56e97；
  复用历史 SDK view 后沙箱无设备，wb01-20260926T153940Z-2-a2fff5。
  未修改系统 SDK。设备访问环境中新探针 verified：
  artifacts/wb01-20260926T154137Z-491033-59f66f/report.json。
- 实际 GPU 命令：HIP_VISIBLE_DEVICES=0 python3 benchmarks/cases/llama-rmsnorm/runner.py
  --hipcc /home/husrcf/Code/ProtBind/wavebridge/artifacts/toolchains/sdk-view-sx4rmd37/bin/hipcc
  --probe-report artifacts/wb01-20260926T154137Z-491033-59f66f/report.json
  --output-base artifacts --nrows 3 --ncols 777 --timeout 60。
- GPU 结果：2331 输出通过，最大绝对误差1.1920928955078125e-07；PCI
  0000:53:00.0 W7900，三个完整性检查点unchanged。报告
  artifacts/wb02-20260926T154202Z-d8e8d1/report.json，SHA256
  50748668e07eb74e231d7ba7a3a3a3d0864de7be8b601310c4f6490279c820ac。
  runner SHA 9c0259ed4b8f74b1cf7f08ae721ead11fba152b44bd457636f321c6c4f243579。
- 局限：一个既有输入的工程回归；不扩大历史九形状证据范围，不运行literal64，
  不证明机器码/静态等价，不建立完整依赖闭包或无竞态消费。配置字段描述
  runner 层请求，SDK wrapper 另含 arch 等选项。独立 IR 观察未当binary证明。
- 工件均本地忽略；check.log/demo.log在上述沙箱no_device目录。文档带结果
  和哈希随提交推送。下一步仍需解决真实候选的归约值与合法目标执行门槛，
  不能用 baseline passed 或额外 manifest 替代自动适配贡献。
